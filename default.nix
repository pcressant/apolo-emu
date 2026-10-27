# Without flakes: nix-build, then ./result/bin/apolo-emu
{ pkgs ? import <nixpkgs> { } }:
pkgs.callPackage ./package.nix { }
