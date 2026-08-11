{
  description = "AnonyMus v3.0 Reproducible Relay & Application Build Flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    rust-overlay.url = "github:oxalica/rust-overlay";
  };

  outputs = { self, nixpkgs, flake-utils, rust-overlay }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        overlays = [ (import rust-overlay) ];
        pkgs = import nixpkgs { inherit system overlays; };
        rustToolchain = pkgs.rust-bin.stable.latest.default.override {
          targets = [ "wasm32-unknown-unknown" ];
        };
      in {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            rustToolchain
            cargo
            rustc
            pkg-config
            openssl
            python311
            uv
            nodejs_20
            wasm-pack
          ];
        };

        packages.anonymus-core = pkgs.rustPlatform.buildRustPackage {
          pname = "anonymus-core";
          version = "3.0.0";
          src = ./core/rust;
          cargoLock.lockFile = ./Cargo.lock;
        };
      });
}
