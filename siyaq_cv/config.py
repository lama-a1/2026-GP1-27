"""Siyaq Sprint 2 engine - every assumption and threshold in one place.

No PyTorch: detection runs an ONNX export of YOLOv8 with onnxruntime (or OpenCV DNN), motion uses
OpenCV Farneback optical flow, so the whole engine fits in a Vercel Python function.
"""
import os

VERSION = "siyaq-cv-sprint2-1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.getenv("SIYAQ_DETECTOR", "yolov8n")             # yolov8n (fast) or yolov8s (more accurate)
MODEL_PATH = os.path.join(HERE, "models", MODEL + ".onnx")

# ---- video
FPS = 10                      # every video is resampled to 10 frames per second (same as the dataset)
WORK_WIDTH = 640              # frames are processed at 640 px width
MAX_SECONDS = float(os.getenv("SIYAQ_MAX_SECONDS", "30"))   # longer videos: only the window around the impact
PRE_IMPACT_S = 22             # window = 22 s before the strongest jolt ... 8 s after it
POST_IMPACT_S = 8

# ---- detection + tracking
CLASSES = {2: "car", 5: "bus", 7: "truck"}      # COCO ids (motorcycles are outside Siyaq's scope)
CONF_HIGH = 0.45              # detections that can start a track
CONF_LOW = 0.20               # weaker detections only extend an existing track (ByteTrack idea)
NMS_IOU = 0.5
MATCH_IOU = 0.25
MAX_LOST = 5                  # frames a track may be missing before it is closed
MIN_TRACK_LEN = 3
LINK_MAX_GAP = 6              # frames: a track that restarts this soon at the predicted place is the same vehicle

# ---- camera assumptions (dashcams are not calibrated, so every metric value is an estimate)
CAMERA_FOV_DEG = 110.0        # horizontal field of view of a typical dashcam
# real heights per class, as in the Vehicle-Distance-Measurement-System reference
REAL_HEIGHT_M = {"car": 1.55, "bus": 3.0, "truck": 2.5}

# ---- optical flow (Farneback, as in the W&B dashcam-speed reference)
FLOW_WIDTH = 320
FARNEBACK = dict(pyr_scale=0.5, levels=3, winsize=15, iterations=3, poly_n=5, poly_sigma=1.2, flags=0)

# ---- events
LANE_SIDE_M = 2.2            # (tuned on train) other vehicle at least this far to the side (m, ground plane) = in a neighbouring lane
LANE_SHIFT_M = 0.4           # (tuned on train) it moved at least this much towards the recording car's lane = lane change
LANE_IN_M = 0.8              # (tuned on train) within this sideways distance it is in front of the recording car
EGO_YAW_DEG = 20.0            # (tuned on train) recording car heading change (from background flow) for its own lane change
TTC_SUDDEN_STOP_S = 1.6      # (tuned on train) time-to-collision of the vehicle ahead below this = sudden stop / hard braking
HEADWAY_FRAC = 0.26          # (tuned on train) box height / width above this = too close
OVERTAKE_MIN_FRAMES = 5
