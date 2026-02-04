{
  description = "Python application with pip requirements";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Create a Python environment with pip-installed requirements
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [ pip virtualenv ]);

      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [ pythonEnv ];

          shellHook = ''
            # Create virtual environment if it doesn't exist
            if [ ! -d .venv ]; then
              echo "Creating virtual environment..."
              python -m venv .venv
            fi

            # Activate virtual environment
            source .venv/bin/activate

            # Install requirements if requirements.txt exists
            if [ -f requirements.txt ]; then
              echo "Installing requirements from requirements.txt..."
              pip install -r requirements.txt
            fi

            echo "Python environment ready!"
            echo "Python version: $(python --version)"
          '';
        };

        # Optional: Create a package for running the application
        packages.default = pkgs.writeShellScriptBin "run-app" ''
          ${pythonEnv}/bin/python main.py "$@"
        '';
      });
}

