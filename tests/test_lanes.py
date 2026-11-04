# Sprint 2: lane lines - TwinLiteNet runs, and solid / dashed is read from the paint along each line
import os, sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from siyaq_cv import config, lanes


def road(dashed_right=True):
    """Grey road, white solid line on the left and a white line on the right (dashed or solid). The mask is
    continuous for both lines, as BDD100K labels dashed lines."""
    img = np.full((360, 640, 3), 70, np.uint8)
    img[300:] = 20                                                      # bonnet
    mask = np.zeros((360, 640), np.uint8)
    cv2.line(img, (170, 299), (300, 180), (235, 235, 235), 7)
    cv2.line(mask, (170, 299), (300, 180), 1, 7)
    cv2.line(mask, (470, 299), (340, 180), 1, 7)
    x = lambda y: int(340 + (y - 180) / 120 * 130)
    step = 15 if dashed_right else 30                                   # dashed: 15 rows of paint, 15 rows of road
    for y in range(180, 300, 30):
        y2 = min(y + step, 299)
        cv2.line(img, (x(y), y), (x(y2), y2), (235, 235, 235), 7)
    return img, mask


def test_solid_and_dashed_from_paint():
    img, mask = road()
    frames = [img] * 6
    _, votes, _ = lanes.analyse(frames, {}, {f: mask for f in range(6)})
    assert lanes.side_type(votes, 'left')[0] == 'Solid'
    assert lanes.side_type(votes, 'right')[0] == 'Dashed'


def test_line_hidden_by_a_vehicle_is_not_called_dashed():
    img, mask = road(dashed_right=False)
    img = img.copy()
    img[225:262, 380:520] = 40                                          # a dark car hides part of the solid right line
    car = {1: {f: (380, 225, 520, 262, 0.9) for f in range(6)}}
    _, votes, _ = lanes.analyse([img] * 6, car, {f: mask for f in range(6)})
    assert lanes.side_type(votes, 'right')[0] != 'Dashed'


def test_twinlitenet_model_runs():
    assert os.path.exists(config.LANE_MODEL_PATH)
    frame = np.full((360, 640, 3), 90, np.uint8)
    m = lanes.masks([frame], [0])
    assert m[0].shape == (360, 640)
