# EER mapping

The seven entities map to seven tables. Composite attributes are flattened into columns. Relationship foreign keys are added on the many side; many-to-many relationships and multivalued bounding boxes need their own tables. The resulting schema has 12 tables.

| EER entity | Table | Primary key | Relationship foreign keys |
| --- | --- | --- | --- |
| ACCIDENT_PARTY | `accident_party` | `national_id` | — |
| VEHICLE | `vehicle` | `vehicle_id` | `national_id` registers/owns the vehicle |
| ACCIDENT_CASE | `accident_case` | `case_id` | `reviewed_by_expert_id` is optional |
| DASHCAM_VIDEO | `dashcam_video` | `video_id` | `case_id`, `national_id` identify its case and uploader |
| DETECTED_EVENT | `detected_event` | `event_id` | `video_id` produces the event |
| AUTHORIZED_EXPERT | `authorized_expert` | `expert_id` | — |
| FINAL_REPORT | `final_report` | `report_id` | unique `case_id`; optional `approved_by_expert_id` |

| EER relationship or attribute | Table | Key and values |
| --- | --- | --- |
| Participates | `participates` | PK (`national_id`, `case_id`) |
| Involves | `involves` | PK (`case_id`, `vehicle_id`) |
| INVOLVEMENT | `involvement` | PK (`event_id`, `vehicle_role`); `event_id` is unique (one vehicle per event); `vehicle_id` FK to the other party's car; `vehicle_role` is ACTOR or AFFECTED; `track_id` |
| Bounding boxes [1..*] | `bounding_box` | PK (`event_id`, `vehicle_role`, `bounding_box`); parent FK to involvement |
| party_a_description / party_b_description (composite) | `accident_case` | one column per part: `party_a_description_text`, `party_a_pre_impact_event`, `party_a_other_vehicle_side`, `party_a_lane_changer`, `party_a_impact_zone` (and the same for `party_b_`) |
| Receives | `receives` | PK (`report_id`, `national_id`) |

`vehicle.manufacturer`, `model`, `year` and `color` are the components of `car_details`. Plate letters and numbers are separate fields. All other entity attributes retain the EER names.

Each case has at most two participants and two linked vehicles. A linked vehicle belongs to a participant, with one vehicle per party in a case. Each party can upload one video per case. An event can involve at most two detected vehicles. A case has at most one final report, with up to two recipients who participate in that case.

Draft cases are allowed while the user enters the required data. Submission requires a participant, a linked vehicle and a video. Both parties and both vehicles are required when the case enters review. PostgreSQL also checks minimum bounding boxes and report recipients through deferred constraints.

In a rear-end case only `party_a_position` is stored; the second party's car is always the opposite position.

This mapping prepares storage for detection and reports. It does not implement automatic analysis, report creation screens or expert approval workflows.

## Supporting tables (not in the EER)

The website needs a few tables that are not part of the EER. They only hold technical data for running the site.

| Table | Why the website needs it |
| --- | --- |
| `participation_progress` | Each party's position (A or B), the step they reached, and whether they submitted |
| `case_invitation` | The private invitation link sent to the second party: its token, expiry and whether it was used |
| `password_reset_link` | Password reset links: token, expiry and whether they were used |
| `login_attempt` | Wrong login attempts, to stop login for 15 minutes after 5 tries |
| `video_processing` | The uploaded file's original name and its privacy/analysis processing status |
| `video_analysis` | Sprint 2: the full result of the automatic analysis of each video (JSON). The events themselves are saved in the EER tables `detected_event`, `involvement` and `bounding_box` |

The tables are created by `schema.py` when the website starts. `database/postgresql.sql` and `database/sqlite.sql` show the same statements.
