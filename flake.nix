{
  description = "Setup python with .venv";

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
        };
      in
      {
        devShells.default = pkgs.mkShell{
          venvDir = ".venv";

          buildInputs = with pkgs; [
            python312
            python312Packages.venvShellHook
            # python312Packages.torch
            # python312Packages.torchvision-bin
            # python312Packages.torchaudio

            uv
          ];


          postVenvCreation = ''
            uv sync
          '';

          shellHook = ''
            venvShellHook
            uv sync
          '';
        };
      });
}
