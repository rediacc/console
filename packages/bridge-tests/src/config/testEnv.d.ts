export declare const TEST_ENV: {
    readonly datastorePath: "/mnt/rediacc";
    readonly uid: "7111";
    readonly network: {
        readonly defaultId: "9152";
        readonly forkA: "9216";
        readonly forkB: "9280";
        readonly defaultCephPgNum: "32";
    };
    readonly vm: {
        readonly bridgeIp: "192.168.111.1";
        readonly worker1Ip: "192.168.111.11";
        readonly worker2Ip: "192.168.111.12";
    };
    readonly rustfs: {
        readonly endpoint: "http://192.168.111.1:9000";
        readonly accessKey: "rustfsadmin";
        readonly secretKey: "rustfsadmin";
        readonly bucket: "rediacc-test";
    };
    readonly testRepositoryPrefix: "test-repo";
    readonly testRepositoryName: "test-repo";
    readonly testContainerPrefix: "test-container";
    readonly testPassword: "test-password-123";
    readonly testUser: "muhammed";
    readonly testTeam: "Test Team";
    /** Installation path for renet on VMs (NOT the local build path) */
    readonly vmRenetInstallPath: "/usr/bin/renet";
};
//# sourceMappingURL=testEnv.d.ts.map