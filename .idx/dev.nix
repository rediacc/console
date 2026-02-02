{ pkgs, ... }: {
  channel = "stable-24.11";

  packages = [
    pkgs.nodejs_22
    pkgs.gh
    pkgs.go
    pkgs.python3
    pkgs.uv
  ];

  env = {
    PORT = "3000";
  };

  idx.extensions = [
    "biomejs.biome"
    "dbaeumer.vscode-eslint"
  ];

  idx.workspace.onCreate = {
    npm-install = "npm install";
    build-packages = "npm run build:packages";
    install-claude = "curl -fsSL https://claude.ai/install.sh | bash";
    install-codex = "npm i -g @openai/codex";
    install-kimi = "uv tool install kimi-cli";
  };

  idx.workspace.onStart = {
    npm-install = "npm install";
  };

  idx.previews = {
    enable = true;
    previews = {
      web = {
        command = ["npm" "run" "dev" "--" "--port" "$PORT" "--host" "0.0.0.0"];
        manager = "web";
      };
    };
  };

  services.docker.enable = true;
}
