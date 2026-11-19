"""Siyaq Sprint 2 engine - every assumption and threshold in one place.

No PyTorch: detection runs an ONNX export of YOLOv8 with onnxruntime (or OpenCV DNN), motion uses
OpenCV Farneback optical flow, so the whole engine fits in a Vercel Python function.
"""
import os

VERSION = "siyaq-cv-sprint2-1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.getenv("SIYAQ_DETECTOR", "yolov8s")             # yolov8s (default, more accurate) or yolov8n (faster)
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

# ---- events (candidate values and their published sources: siyaq_cv/threshold_grid.py)
LANE_SIDE_M = 2.0            # (used only when the report type is unknown; per type: LANE_BY_TYPE) other vehicle at least this far to the side (m, ground plane) = in a neighbouring lane
LANE_SHIFT_M = 0.3           # (used only when the report type is unknown; per type: LANE_BY_TYPE) it moved at least this much towards the recording car's lane = lane change
LANE_VEL_HALF = 2             # inward speed from positions +-2 frames apart
LANE_ONSET_MPS = 0.6         # (used only when the report type is unknown; per type: LANE_BY_TYPE) inward speed = moving into the lane
EDGE_PX = 2                   # a box this close to the left/right image side is cut by the picture
LANE_IN_M = 0.6              # (used only when the report type is unknown; per type: LANE_BY_TYPE) within this sideways distance it is in front of the recording car
EGO_YAW_DEG = 16.0            # (used only when the report type is unknown; per type: LANE_BY_TYPE) recording car heading change (from background flow) for its own lane change
COLLISION_SIZE_MIN = 0.85    # impact candidates: B at least this share of its largest size in the clip
                              # (149 clips with ByteTrack: 71.1% within 0.5 s of the annotated impact, 11.4% later)
TTC_SUDDEN_STOP_S = 2.0      # (repeated 5x5 CV with YOLOv8s, chosen on all 136 clips, 2026-11-19) time-to-collision of the vehicle ahead below this = sudden stop / hard braking
# Safe following distance. Research judges it by the time headway (gap / own speed: 2-second rule; 0.9-3.0 s in
# Vogel 2003), which needs the recording car's speed - not measurable reliably from the video. Siyaq uses the
# time-to-collision with Vehicle B instead, the other standard surrogate safety measure (critical value 1.5 s,
# van der Horst 1991; 1.5-3 s common; 4.5 s calibrated on naturalistic driving data, Lu et al. 2021).
SAFE_TTC_S = 4.5              # (repeated 5x5 CV with YOLOv8s, chosen on all 136 clips, 2026-11-19) TTC below this at SAFE_REF_S before the impact = safe distance not maintained
SAFE_REF_S = 1.5              # seconds before the impact at which it is judged (in the last second every rear-end
                              # approach has a small TTC). Both values are chosen by tools/cross_validate.py.
# Lane-change thresholds per accident type of the user's report (they replace the five LANE_*/EGO_YAW_DEG values above,
# which are used only when the type is unknown). Chosen per report type by tools/cross_validate.py.
LANE_BY_TYPE = {   # repeated 5x5 CV with YOLOv8s, chosen on all 136 clips per report type, 2026-11-19
    "REAR_END": {"LANE_SIDE_M": 1.0, "LANE_SHIFT_M": 1.5, "LANE_IN_M": 0.6, "LANE_ONSET_MPS": 0.2, "EGO_YAW_DEG": 20.0, "LANE_LINE_RULE": "and"},
    "LANE_CHANGE": {"LANE_SIDE_M": 1.0, "LANE_SHIFT_M": 0.3, "LANE_IN_M": 0.6, "LANE_ONSET_MPS": 0.6, "EGO_YAW_DEG": 2.0, "LANE_LINE_RULE": "off"},
}
LANE_LINE_RULE = "off"        # Vehicle B's lane change from the lane lines: "off", "or" (add), "and" (confirm), "line" (both)
LANE_LINE_MIN_FRAMES = 3      # lane-analysed frames with a usable line needed before the lines are used
LANE_LINE_MIN_IN = 2          # B must stay inside the lane for this many analysed frames after crossing
LANE_DETECT_MPS = None        # optional: B's inward lateral speed must reach this (m/s) for a lane change; None = no check
SAFE_TTC_MODE = "at_ref"     # "at_ref": TTC at SAFE_REF_S before the impact; "min_before_ref": minimum TTC up to that moment
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
