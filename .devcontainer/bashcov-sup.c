// Source of truth for the bashcov supervisor. Built into the devbox image by the Dockerfile
// and onto the host by run.sh setup (both to bashcov-sup on PATH). See
// agent/PLAN-shell-resource-profiling.md section 1c for what it survives and why.
// bashcov candidate F: supervisor. Usage: bashcov-sup -- cmd args...
// fork+exec the command; forward termination signals; sample /proc/<pid>/wchan
// while it runs; wait4 for tree rusage; write one JSON record; exit like the child.
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <time.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <sys/prctl.h>
static pid_t child;
static void fwd(int sig){ if(child>0) kill(child,sig); }
#define NW 8
static char wname[NW][128]; static int wcnt[NW]; static int nsamp, nblocked;
static long peak_hwm;
// BASHCOV_SHAPE is the record's only text field, and it is deliberately NOT the
// command. bash.jsonl carried pids, rusage and kernel symbols but no script
// identity, so 35 MB a day could not be attributed to anything and nothing read it
// -- the write-only shape the gate's kill trigger exists to punish. The env var is
// set by bash_env.sh from $0 (a repo-relative path) or a fixed literal for -c/-s;
// BASH_EXECUTION_STRING is never used, because a command line in a public repo can
// carry a secret. Copied here with a length bound and printable-ASCII filtering so
// a hostile value cannot break the JSON.
static void esc_shape(char*dst,size_t cap){
    const char*s=getenv("BASHCOV_SHAPE"); size_t j=0;
    if(!s){ dst[0]=0; return; }
    for(size_t i=0;s[i]&&j+2<cap;i++){
        unsigned char c=(unsigned char)s[i];
        if(c=='"'||c=='\\'){ dst[j++]='\\'; dst[j++]=(char)c; }
        else if(c>=0x20&&c<0x7f){ dst[j++]=(char)c; }
    }
    dst[j]=0;
}
static void sample(void){
    char p[64], buf[128]; int fd, n;
    snprintf(p,sizeof p,"/proc/%d/wchan",child);
    fd=open(p,O_RDONLY); if(fd<0) return; n=read(fd,buf,sizeof buf-1); close(fd); if(n<=0) return; buf[n]=0;
    nsamp++;
    if(strcmp(buf,"0")!=0){ nblocked++; int i; for(i=0;i<NW;i++){ if(wcnt[i]==0){snprintf(wname[i],sizeof wname[i],"%s",buf);wcnt[i]=1;break;} if(!strcmp(wname[i],buf)){wcnt[i]++;break;} } }
    snprintf(p,sizeof p,"/proc/%d/status",child);
    FILE*f=fopen(p,"r"); if(f){ char l[256]; while(fgets(l,sizeof l,f)){ if(!strncmp(l,"VmHWM:",6)){ long v=atol(l+6); if(v>peak_hwm)peak_hwm=v; break;} } fclose(f);}
}
int main(int argc,char**argv){
    if(argc<3||strcmp(argv[1],"--")){ fprintf(stderr,"usage: bashcov-sup -- cmd...\n"); return 2; }
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0);
    sigset_t m; sigemptyset(&m); sigaddset(&m,SIGCHLD); sigprocmask(SIG_BLOCK,&m,NULL);
    child=fork();
    if(child<0){ execvp(argv[2],argv+2); _exit(127); }      /* cannot fork: run unwrapped */
    if(child==0){
        sigprocmask(SIG_UNBLOCK,&m,NULL);
        char b[32]; snprintf(b,sizeof b,"%d",(int)getppid()); setenv("__BASHCOV_SUP",b,1);
        prctl(PR_SET_PDEATHSIG,SIGKILL);
        execvp(argv[2],argv+2); perror(argv[2]); _exit(127);
    }
    int s[]={SIGINT,SIGTERM,SIGHUP,SIGQUIT,SIGUSR1,SIGUSR2,SIGPIPE,SIGALRM};
    for(unsigned i=0;i<sizeof s/sizeof*s;i++){ struct sigaction sa={0}; sa.sa_handler=fwd; sigaction(s[i],&sa,NULL); }
    signal(SIGTTIN,SIG_IGN); signal(SIGTTOU,SIG_IGN);
    struct timespec iv={0,250000000};
    for(;;){ siginfo_t si; int r=sigtimedwait(&m,&si,&iv); if(r<0&&errno==EAGAIN){ sample(); continue;} if(r<0&&errno==EINTR) continue; break; }
    int st=0; struct rusage ru; while(wait4(child,&st,0,&ru)<0&&errno==EINTR);
    clock_gettime(CLOCK_MONOTONIC,&t1);
    const char*out=getenv("BASHCOV_OUT");
    if(out){ int fd=open(out,O_WRONLY|O_APPEND|O_CREAT|O_CLOEXEC,0600); if(fd>=0){
        char shp[192]; esc_shape(shp,sizeof shp);
        char buf[1280]; int n=snprintf(buf,sizeof buf,"{\"src\":\"sup\",\"shape\":\"%s\",\"pid\":%d,\"sup\":%d,\"ppid\":%d,\"exit\":%d,\"sig\":%d,\"wall_us\":%ld,\"utime_us\":%ld,\"stime_us\":%ld,\"maxrss_kb\":%ld,\"peak_hwm_kb\":%ld,\"nvcsw\":%ld,\"nivcsw\":%ld,\"samples\":%d,\"blocked\":%d,\"wchan\":[",
            shp,(int)child,(int)getpid(),(int)getppid(),WIFEXITED(st)?WEXITSTATUS(st):-1,WIFSIGNALED(st)?WTERMSIG(st):0,
            (long)((t1.tv_sec-t0.tv_sec)*1000000L+(t1.tv_nsec-t0.tv_nsec)/1000),
            ru.ru_utime.tv_sec*1000000L+ru.ru_utime.tv_usec,ru.ru_stime.tv_sec*1000000L+ru.ru_stime.tv_usec,ru.ru_maxrss,peak_hwm,ru.ru_nvcsw,ru.ru_nivcsw,nsamp,nblocked);
        for(int i=0;i<NW&&wcnt[i]&&n<(int)sizeof buf-80;i++) n+=snprintf(buf+n,sizeof buf-n,"%s[\"%s\",%d]",i?",":"",wname[i],wcnt[i]);
        n+=snprintf(buf+n,sizeof buf-n,"]}\n"); ssize_t w=write(fd,buf,n); (void)w; close(fd); } }
    if(WIFSIGNALED(st)){ int sg=WTERMSIG(st); signal(sg,SIG_DFL); raise(sg); _exit(128+sg); }
    return WEXITSTATUS(st);
}
