# Maintainer: pcressant
# Local-checkout recipe: run makepkg from the complete project directory.
# No remote source is configured while the project remains unpublished.

pkgname=apolo-emu
pkgver=0.1.0
pkgrel=1
pkgdesc='Dolphin Apollo II speech synthesizer emulator'
arch=('any')
license=('MIT')
depends=('python>=3.10')
makedepends=('python-build' 'python-installer' 'python-setuptools>=77')
checkdepends=('qemu-system-x86')
optdepends=(
  'speech-dispatcher: speech output through the SSIP backend'
  'espeak-ng: recommended Speech Dispatcher speech engine'
  'qemu-system-x86: start an x86 virtual machine with the integrated launcher'
)
source=()
sha256sums=()

build() {
  cd "$startdir" || return 1
  python -m build --wheel --no-isolation --outdir "$srcdir/dist"
}

check() {
  cd "$startdir" || return 1
  # Use the independent QEMU test VM; never produce sound during package checks.
  APOLO_EMU_SPEECHD='' APOLO_EMU_SKIP_QEMU='' \
    python -m unittest discover -s tests -t .
}

package() {
  cd "$startdir" || return 1
  python -m installer --destdir="$pkgdir" --prefix=/usr \
    "$srcdir/dist/apolo_emu-$pkgver-py3-none-any.whl"

  install -Dm644 LICENSE NOTICE.md NOTICE-fr.md \
    -t "$pkgdir/usr/share/licenses/$pkgname"
  install -Dm644 README.md README-fr.md \
    -t "$pkgdir/usr/share/doc/$pkgname"
  install -Dm644 docs/*.md -t "$pkgdir/usr/share/doc/$pkgname/docs"
}
