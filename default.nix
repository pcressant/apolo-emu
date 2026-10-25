# Sans flake : nix-build, puis ./result/bin/apolo-emu
{ pkgs ? import <nixpkgs> { } }:
pkgs.callPackage ./package.nix { }
