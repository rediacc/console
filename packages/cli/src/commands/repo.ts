import { Command } from "commander";
import { t } from "../i18n/index.js";
import { contextService } from "../services/context.js";
import { localExecutorService } from "../services/local-executor.js";
import { outputService } from "../services/output.js";
import { handleError } from "../utils/errors.js";

/**
 * Execute a repository lifecycle function on a remote machine.
 * Validates the repository exists in context and runs the function via localExecutorService.
 */
async function executeRepoFunction(
  functionName: string,
  repoName: string,
  machineName: string,
  params: Record<string, unknown>,
  options: { debug?: boolean },
  messages: { starting: string; completed: string; failed: string },
): Promise<void> {
  // Validate repository exists in context
  const repo = await contextService.getLocalRepository(repoName);
  if (!repo) {
    throw new Error(`Repository "${repoName}" not found in context`);
  }
  if (!repo.credential) {
    outputService.warn(t("commands.repo.noCredential", { name: repoName }));
  }

  // Ensure network_id is assigned (auto-allocates for legacy repos without one)
  await contextService.ensureRepositoryNetworkId(repoName);

  outputService.info(messages.starting);

  const result = await localExecutorService.execute({
    functionName,
    machineName,
    params: { repository: repoName, ...params },
    debug: options.debug,
  });

  if (result.success) {
    outputService.success(messages.completed);
  } else {
    outputService.error(messages.failed);
    process.exitCode = result.exitCode;
  }
}

export function registerRepoCommands(program: Command): void {
  const repo = program
    .command("repo")
    .description(t("commands.repo.description"));

  // repo mount <name>
  repo
    .command("mount <name>")
    .description(t("commands.repo.mount.description"))
    .requiredOption("-m, --machine <name>", t("commands.repo.machineOption"))
    .option("--checkpoint", t("commands.repo.mount.checkpointOption"))
    .option("--debug", t("options.debug"))
    .action(
      async (
        name: string,
        options: { machine: string; checkpoint?: boolean; debug?: boolean },
      ) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.checkpoint) params.checkpoint = true;

          await executeRepoFunction(
            "repository_mount",
            name,
            options.machine,
            params,
            options,
            {
              starting: t("commands.repo.mount.starting", {
                repository: name,
                machine: options.machine,
              }),
              completed: t("commands.repo.mount.completed"),
              failed: t("commands.repo.mount.failed"),
            },
          );
        } catch (error) {
          handleError(error);
        }
      },
    );

  // repo unmount <name>
  repo
    .command("unmount <name>")
    .description(t("commands.repo.unmount.description"))
    .requiredOption("-m, --machine <name>", t("commands.repo.machineOption"))
    .option("--checkpoint", t("commands.repo.unmount.checkpointOption"))
    .option("--debug", t("options.debug"))
    .action(
      async (
        name: string,
        options: { machine: string; checkpoint?: boolean; debug?: boolean },
      ) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.checkpoint) params.checkpoint = true;

          await executeRepoFunction(
            "repository_unmount",
            name,
            options.machine,
            params,
            options,
            {
              starting: t("commands.repo.unmount.starting", {
                repository: name,
                machine: options.machine,
              }),
              completed: t("commands.repo.unmount.completed"),
              failed: t("commands.repo.unmount.failed"),
            },
          );
        } catch (error) {
          handleError(error);
        }
      },
    );

  // repo up <name>
  repo
    .command("up <name>")
    .description(t("commands.repo.up.description"))
    .requiredOption("-m, --machine <name>", t("commands.repo.machineOption"))
    .option("--mount", t("commands.repo.up.mountOption"))
    .option("--prep-only", t("commands.repo.up.prepOnlyOption"))
    .option("--grand <name>", t("commands.repo.up.grandOption"))
    .option("--debug", t("options.debug"))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          mount?: boolean;
          prepOnly?: boolean;
          grand?: string;
          debug?: boolean;
        },
      ) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.mount) params.mount = true;
          if (options.prepOnly) params.option = "prep-only";

          // Resolve grand repo friendly name → GUID
          if (options.grand) {
            const grandRepo = await contextService.getLocalRepository(
              options.grand,
            );
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          await executeRepoFunction(
            "repository_up",
            name,
            options.machine,
            params,
            options,
            {
              starting: t("commands.repo.up.starting", {
                repository: name,
                machine: options.machine,
              }),
              completed: t("commands.repo.up.completed"),
              failed: t("commands.repo.up.failed"),
            },
          );
        } catch (error) {
          handleError(error);
        }
      },
    );

  // repo down <name>
  repo
    .command("down <name>")
    .description(t("commands.repo.down.description"))
    .requiredOption("-m, --machine <name>", t("commands.repo.machineOption"))
    .option("--unmount", t("commands.repo.down.unmountOption"))
    .option("--grand <name>", t("commands.repo.down.grandOption"))
    .option("--debug", t("options.debug"))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          unmount?: boolean;
          grand?: string;
          debug?: boolean;
        },
      ) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.unmount) params.option = "unmount";

          // Resolve grand repo friendly name → GUID
          if (options.grand) {
            const grandRepo = await contextService.getLocalRepository(
              options.grand,
            );
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          await executeRepoFunction(
            "repository_down",
            name,
            options.machine,
            params,
            options,
            {
              starting: t("commands.repo.down.starting", {
                repository: name,
                machine: options.machine,
              }),
              completed: t("commands.repo.down.completed"),
              failed: t("commands.repo.down.failed"),
            },
          );
        } catch (error) {
          handleError(error);
        }
      },
    );

  // repo status <name>
  repo
    .command("status <name>")
    .description(t("commands.repo.status.description"))
    .requiredOption("-m, --machine <name>", t("commands.repo.machineOption"))
    .option("--debug", t("options.debug"))
    .action(
      async (name: string, options: { machine: string; debug?: boolean }) => {
        try {
          await executeRepoFunction(
            "repository_status",
            name,
            options.machine,
            {},
            options,
            {
              starting: t("commands.repo.status.starting", {
                repository: name,
                machine: options.machine,
              }),
              completed: t("commands.repo.status.completed"),
              failed: t("commands.repo.status.failed"),
            },
          );
        } catch (error) {
          handleError(error);
        }
      },
    );

  // repo list (no positional arg — lists all repos on the machine)
  repo
    .command("list")
    .description(t("commands.repo.list.description"))
    .requiredOption("-m, --machine <name>", t("commands.repo.machineOption"))
    .option("--debug", t("options.debug"))
    .action(async (options: { machine: string; debug?: boolean }) => {
      try {
        outputService.info(
          t("commands.repo.list.starting", { machine: options.machine }),
        );

        const result = await localExecutorService.execute({
          functionName: "repository_list",
          machineName: options.machine,
          params: {},
          debug: options.debug,
        });

        if (result.success) {
          outputService.success(t("commands.repo.list.completed"));
        } else {
          outputService.error(
            t("commands.repo.list.failed", { error: result.error }),
          );
          process.exitCode = result.exitCode;
        }
      } catch (error) {
        handleError(error);
      }
    });
}
