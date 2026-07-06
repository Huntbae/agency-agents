"""Generate demo assets (thin wrapper around mvstudio.demo).

Usage: python examples/make_demo_assets.py [outdir]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from mvstudio.demo import make_images, make_song

if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else "demo_assets"
    os.makedirs(outdir, exist_ok=True)
    print("wrote", make_song(os.path.join(outdir, "demo.wav")))
    print("wrote", make_images(os.path.join(outdir, "images")))
