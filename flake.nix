{
  description = "Setup development environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          system = system;
          config.cudaSupport = true;
          config.cudnnSupport = true;
          config.allowUnfree = true;
        };

        # Python environment
        pythonEnv = pkgs.python313.withPackages (pkgs: with pkgs; [
          #llama-index
          #llama-index-embeddings-openai
          openai
          watchdog
          numpy
          langchain-community
          langchain-text-splitters
          langchain-openai
          faiss
          mcp
          langgraph
          aiohttp
          aiohttp-cors
          pytest
          pytest-asyncio
        ]);
      in
      {
        devShells.default = pkgs.mkShell{

          buildInputs = with pkgs; [
            pythonEnv
            gh-copilot
            gh
          ];


          shellHook = ''
            # Python path
            export PYTHONPATH="${pythonEnv}/${pythonEnv.sitePackages}:$PYTHONPATH"
            export PYTHONPATH=$PYTHONPATH:$(pwd)

            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH"
            export MCP_VERSION="0.1.0"
          '';
        };

        packages.default = pkgs.python313Packages.buildPythonPackage {
          pname = "echo-mcp";
          version = "0.1.0";
          src = ./.;

          pyproject = true;
          build-system = [ pkgs.python313Packages.setuptools ];

          propagatedBuildInputs = [
            pythonEnv
          ];
        };

        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/echo-mcp";
        };
      });
}
