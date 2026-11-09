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
COLLISION_SIZE_MIN = 0.85    # impact candidates: B at least this share of its largest size in the clip
                              # (149 clips with ByteTrack: 71.1% within 0.5 s of the annotated impact, 11.4% later)
TTC_SUDDEN_STOP_S = 1.6      # (tuned on train) time-to-collision of the vehicle ahead below this = sudden stop / hard braking
LANE_WIDTH_M = 3.6            # a highway lane (only used to draw the recording car's lane on the expert's chart)
HEADWAY_FRAC = 0.26          # (tuned on train) box height / width above this = too close
OVERTAKE_MIN_FRAMES = 5

# ---- lane lines (TwinLiteNet, lane-line segmentation trained on BDD100K, MIT licence)
LANE_MODEL_PATH = os.path.join(HERE, "models", "twinlitenet.onnx")
LANE_SECONDS = 5              # lane lines are read in the last 5 s before the impact ...
LANE_STEP = 2                 # ... on every 2nd frame (the model takes about 0.5 s a frame on a CPU)
LANE_MIN_PIXELS = 25          # smaller mask pieces are noise
LANE_JOIN_PX = 12             # pieces within this many mask pixels of one straight line = one lane line
LANE_BAND_FRAC = 0.28         # road band above the bonnet used to judge the line (share of image height)
LANE_MIN_BAND_ROWS = 25       # the line must be visible on at least this many rows of the band
LANE_PAINT_W = 8             # half-width of a lane line at the bottom of the 640x360 image (px)
LANE_PAINT_CONTRAST = 18      # paint is at least this much brighter (0-255) than the road beside it
LANE_MIN_COVER = 0.15         # less paint than this in the band = cannot judge
LANE_SOLID_COVER = 0.90       # paint on at least this share of the rows and no real gap = solid
LANE_GAP_ROWS = 6             # a gap this long (mask rows) with paint on both sides = dashed
LANE_MIN_VOTES = 3            # frames with a typed line needed before saying solid / dashed
LANE_VOTE = 0.65              # share of those frames that must agree

# ---- tracker: "bytetrack" (official algorithm, Kalman filter + Hungarian matching) or "iou" (the light Sprint 2 tracker)
TRACKER = os.getenv("SIYAQ_TRACKER", "bytetrack")
BT_TRACK_THRESH = 0.5         # ByteTrack defaults (official repo): high-score detections
BT_LOW_THRESH = 0.1           # low-score detections used in the second association
BT_MATCH_THRESH = 0.8         # first association: 1 - IoU (fused with the score) must be at most this
BT_BOX = os.getenv("SIYAQ_BT_BOX", "kalman")   # box reported per frame: "kalman" (official) or "detection"
BT_TRACK_BUFFER = 30          # frames at 30 fps a lost track is kept (scaled to 10 fps = 10 frames)
