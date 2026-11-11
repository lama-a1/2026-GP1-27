-- Run once in the Neon SQL Editor, right after this update is deployed.
-- It changes the existing tables to match the final EER and keeps the saved data.

-- 1) Involved: events are linked to the other party's car (ACTOR / AFFECTED); detected_vehicle is removed.
--    The analysis tables are recreated by the website, then analyse the videos again.
DROP TABLE IF EXISTS bounding_box, involvement, detected_vehicle CASCADE;
DROP FUNCTION IF EXISTS involvement_max_two_check() CASCADE;

-- 2) LOGIN_ATTEMPT.lock_expiration
ALTER TABLE login_attempt RENAME COLUMN locked_until TO lock_expiration;

-- 3) composite attributes party_a_description / party_b_description: one column per part in accident_case
ALTER TABLE accident_case RENAME COLUMN party_a_description TO party_a_description_text;
ALTER TABLE accident_case RENAME COLUMN party_b_description TO party_b_description_text;
ALTER TABLE accident_case
    ADD COLUMN IF NOT EXISTS party_a_pre_impact_event TEXT, ADD COLUMN IF NOT EXISTS party_a_other_vehicle_side TEXT,
    ADD COLUMN IF NOT EXISTS party_a_lane_changer TEXT, ADD COLUMN IF NOT EXISTS party_a_impact_zone TEXT,
    ADD COLUMN IF NOT EXISTS party_b_pre_impact_event TEXT, ADD COLUMN IF NOT EXISTS party_b_other_vehicle_side TEXT,
    ADD COLUMN IF NOT EXISTS party_b_lane_changer TEXT, ADD COLUMN IF NOT EXISTS party_b_impact_zone TEXT;

-- copy the choices of the cases saved before this update
UPDATE accident_case ca SET
    party_a_pre_impact_event = pp.description_meta::json->>'rcase',
    party_a_other_vehicle_side = pp.description_meta::json->>'side',
    party_a_lane_changer = pp.description_meta::json->>'who',
    party_a_impact_zone = pp.description_meta::json->>'zone'
FROM participation_progress pp
WHERE pp.case_id = ca.case_id AND pp.position = 'A' AND pp.description_meta IS NOT NULL AND pp.description_meta <> '';
UPDATE accident_case ca SET
    party_b_pre_impact_event = pp.description_meta::json->>'rcase',
    party_b_other_vehicle_side = pp.description_meta::json->>'side',
    party_b_lane_changer = pp.description_meta::json->>'who',
    party_b_impact_zone = pp.description_meta::json->>'zone'
FROM participation_progress pp
WHERE pp.case_id = ca.case_id AND pp.position = 'B' AND pp.description_meta IS NOT NULL AND pp.description_meta <> '';

ALTER TABLE participation_progress DROP COLUMN IF EXISTS description_meta;
