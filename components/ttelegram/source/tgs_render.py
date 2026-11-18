"""Decode Telegram vector stickers in a separate process."""
import sys
from rlottie_python import LottieAnimation
with LottieAnimation.from_tgs(sys.argv[1]) as animation:
    if sys.argv[2].endswith('.gif'):animation.save_animation(sys.argv[2])
    else:animation.save_frame(sys.argv[2],frame_num=0)
