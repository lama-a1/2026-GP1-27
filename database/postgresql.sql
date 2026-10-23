-- Siyaq EER schema

CREATE TABLE IF NOT EXISTS accident_party (
            national_id TEXT PRIMARY KEY NOT NULL, full_name TEXT NOT NULL, date_of_birth TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            notify_status_change INTEGER NOT NULL DEFAULT 1 CHECK (notify_status_change IN (0,1)),
            notify_final_result INTEGER NOT NULL DEFAULT 1 CHECK (notify_final_result IN (0,1)));

CREATE TABLE IF NOT EXISTS authorized_expert (
            expert_id BIGSERIAL PRIMARY KEY, full_name TEXT NOT NULL, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS vehicle (
            vehicle_id BIGSERIAL PRIMARY KEY, plate_number TEXT NOT NULL CHECK (length(plate_number) BETWEEN 1 AND 4),
            plate_letters TEXT NOT NULL CHECK (length(plate_letters) BETWEEN 1 AND 8),
            manufacturer TEXT NOT NULL, model TEXT NOT NULL, year INTEGER NOT NULL, color TEXT NOT NULL,
            national_id TEXT NOT NULL REFERENCES accident_party(national_id));

CREATE TABLE IF NOT EXISTS accident_case (
            case_id TEXT PRIMARY KEY NOT NULL, party_b_email TEXT, accident_type TEXT NOT NULL
                CHECK (accident_type IN ('REAR_END','LANE_CHANGE')),
            party_a_position TEXT CHECK (party_a_position IN ('FRONT','REAR')),
            accident_date TEXT NOT NULL, accident_time TEXT NOT NULL, location TEXT NOT NULL,
            party_a_description TEXT, party_b_description TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            reviewed_by_expert_id BIGINT REFERENCES authorized_expert(expert_id));

CREATE TABLE IF NOT EXISTS participates (
            national_id TEXT NOT NULL REFERENCES accident_party(national_id),
            case_id TEXT NOT NULL REFERENCES accident_case(case_id) ON DELETE CASCADE,
            PRIMARY KEY (national_id,case_id));

CREATE TABLE IF NOT EXISTS involves (
            case_id TEXT NOT NULL REFERENCES accident_case(case_id) ON DELETE CASCADE,
            vehicle_id BIGINT NOT NULL REFERENCES vehicle(vehicle_id),
            PRIMARY KEY (case_id,vehicle_id));

CREATE TABLE IF NOT EXISTS dashcam_video (
            video_id BIGSERIAL PRIMARY KEY, storage_path TEXT NOT NULL UNIQUE,
            camera_type TEXT NOT NULL CHECK (camera_type IN ('front','rear')),
            uploaded_at TEXT NOT NULL DEFAULT (to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS')), case_id TEXT NOT NULL,
            national_id TEXT NOT NULL, UNIQUE (case_id,national_id),
            FOREIGN KEY (national_id,case_id) REFERENCES participates(national_id,case_id) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS detected_event (
            event_id BIGSERIAL PRIMARY KEY, event_type TEXT NOT NULL, event_value TEXT, frame_path TEXT,
            start_time DOUBLE PRECISION NOT NULL, end_time DOUBLE PRECISION NOT NULL CHECK (end_time >= start_time),
            video_id BIGINT NOT NULL REFERENCES dashcam_video(video_id) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS detected_vehicle (
            detected_vehicle_id BIGSERIAL PRIMARY KEY, vehicle_id BIGINT REFERENCES vehicle(vehicle_id));

CREATE TABLE IF NOT EXISTS involvement (
            event_id BIGINT NOT NULL REFERENCES detected_event(event_id) ON DELETE CASCADE,
            detected_vehicle_id BIGINT NOT NULL REFERENCES detected_vehicle(detected_vehicle_id),
            vehicle_role TEXT NOT NULL, track_id TEXT NOT NULL,
            PRIMARY KEY (event_id,vehicle_role), UNIQUE (event_id,detected_vehicle_id));

CREATE TABLE IF NOT EXISTS bounding_box (
            event_id BIGINT NOT NULL, vehicle_role TEXT NOT NULL, bounding_box TEXT NOT NULL,
            PRIMARY KEY (event_id,vehicle_role,bounding_box),
            FOREIGN KEY (event_id,vehicle_role) REFERENCES involvement(event_id,vehicle_role) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS final_report (
            report_id BIGSERIAL PRIMARY KEY, outcome TEXT, suggested_party_a_fault DOUBLE PRECISION,
            suggested_party_b_fault DOUBLE PRECISION, party_a_fault DOUBLE PRECISION, party_b_fault DOUBLE PRECISION,
            undetermined_code TEXT, applied_rule TEXT, expert_notes TEXT, final_description TEXT,
            approved_at TEXT, case_id TEXT NOT NULL UNIQUE REFERENCES accident_case(case_id) ON DELETE CASCADE,
            approved_by_expert_id BIGINT REFERENCES authorized_expert(expert_id));

CREATE TABLE IF NOT EXISTS receives (
            report_id BIGINT NOT NULL REFERENCES final_report(report_id) ON DELETE CASCADE,
            national_id TEXT NOT NULL REFERENCES accident_party(national_id),
            PRIMARY KEY (report_id,national_id));

CREATE TABLE IF NOT EXISTS participation_progress (
            national_id TEXT NOT NULL, case_id TEXT NOT NULL,
            position TEXT NOT NULL CHECK (position IN ('A','B')),
            progress INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0,1)),
            description_meta TEXT, joined_at TEXT NOT NULL DEFAULT (to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS')),
            PRIMARY KEY (national_id,case_id), UNIQUE (case_id,position),
            FOREIGN KEY (national_id,case_id) REFERENCES participates(national_id,case_id) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS case_invitation (
            invitation_id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL REFERENCES accident_case(case_id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE, recipient_email TEXT NOT NULL, expires_at TEXT NOT NULL,
            claimed_by TEXT REFERENCES accident_party(national_id), revoked_at TEXT,
            created_at TEXT NOT NULL DEFAULT (to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS')));

CREATE TABLE IF NOT EXISTS password_reset_link (
            link_id BIGSERIAL PRIMARY KEY, national_id TEXT NOT NULL REFERENCES accident_party(national_id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE, expires_at DOUBLE PRECISION NOT NULL, used_at TEXT);

CREATE TABLE IF NOT EXISTS login_attempt (
            key TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, locked_until DOUBLE PRECISION);

CREATE TABLE IF NOT EXISTS video_processing (
            video_id BIGINT PRIMARY KEY REFERENCES dashcam_video(video_id) ON DELETE CASCADE,
            original_name TEXT NOT NULL, processed_path TEXT,
            privacy_status TEXT NOT NULL DEFAULT 'pending', note TEXT,
            job_status TEXT NOT NULL DEFAULT 'queued', job_details TEXT,
            updated_at TEXT NOT NULL DEFAULT (to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS')));

CREATE INDEX IF NOT EXISTS participates_case_idx ON participates(case_id);

CREATE INDEX IF NOT EXISTS vehicle_owner_idx ON vehicle(national_id);

CREATE INDEX IF NOT EXISTS dashcam_case_idx ON dashcam_video(case_id);

CREATE OR REPLACE FUNCTION participates_max_two_check() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF TG_OP='UPDATE' AND OLD.case_id=NEW.case_id THEN RETURN NEW; END IF;
                    PERFORM 1 FROM accident_case
                    WHERE case_id = NEW.case_id FOR UPDATE;
                    IF (SELECT count(*) FROM participates WHERE case_id=NEW.case_id) >= 2 THEN RAISE EXCEPTION 'A case can have at most two accident parties'; END IF;
                    RETURN NEW;
                END $$;

DROP TRIGGER IF EXISTS participates_max_two ON participates;

CREATE TRIGGER participates_max_two BEFORE INSERT OR UPDATE ON participates FOR EACH ROW EXECUTE FUNCTION participates_max_two_check();

CREATE OR REPLACE FUNCTION involves_max_two_check() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF TG_OP='UPDATE' AND OLD.case_id=NEW.case_id THEN RETURN NEW; END IF;
                    PERFORM 1 FROM accident_case
                    WHERE case_id = NEW.case_id FOR UPDATE;
                    IF (SELECT count(*) FROM involves WHERE case_id=NEW.case_id) >= 2 THEN RAISE EXCEPTION 'A case can involve at most two vehicles'; END IF;
                    RETURN NEW;
                END $$;

DROP TRIGGER IF EXISTS involves_max_two ON involves;

CREATE TRIGGER involves_max_two BEFORE INSERT OR UPDATE ON involves FOR EACH ROW EXECUTE FUNCTION involves_max_two_check();

CREATE OR REPLACE FUNCTION involvement_max_two_check() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF TG_OP='UPDATE' AND OLD.event_id=NEW.event_id THEN RETURN NEW; END IF;
                    PERFORM 1 FROM detected_event
                    WHERE event_id = NEW.event_id FOR UPDATE;
                    IF (SELECT count(*) FROM involvement WHERE event_id=NEW.event_id) >= 2 THEN RAISE EXCEPTION 'An event can involve at most two detected vehicles'; END IF;
                    RETURN NEW;
                END $$;

DROP TRIGGER IF EXISTS involvement_max_two ON involvement;

CREATE TRIGGER involvement_max_two BEFORE INSERT OR UPDATE ON involvement FOR EACH ROW EXECUTE FUNCTION involvement_max_two_check();

CREATE OR REPLACE FUNCTION receives_max_two_check() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF TG_OP='UPDATE' AND OLD.report_id=NEW.report_id THEN RETURN NEW; END IF;
                    PERFORM 1 FROM final_report
                    WHERE report_id = NEW.report_id FOR UPDATE;
                    IF (SELECT count(*) FROM receives WHERE report_id=NEW.report_id) >= 2 THEN RAISE EXCEPTION 'A report can have at most two recipients'; END IF;
                    RETURN NEW;
                END $$;

DROP TRIGGER IF EXISTS receives_max_two ON receives;

CREATE TRIGGER receives_max_two BEFORE INSERT OR UPDATE ON receives FOR EACH ROW EXECUTE FUNCTION receives_max_two_check();

CREATE OR REPLACE FUNCTION involves_owner_check() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NOT EXISTS (
            SELECT 1 FROM vehicle v JOIN participates p ON p.national_id=v.national_id
            WHERE v.vehicle_id=NEW.vehicle_id AND p.case_id=NEW.case_id) THEN RAISE EXCEPTION 'Vehicle owner must participate in this case'; END IF; RETURN NEW; END $$;

DROP TRIGGER IF EXISTS involves_owner ON involves;

CREATE TRIGGER involves_owner BEFORE INSERT OR UPDATE ON involves FOR EACH ROW EXECUTE FUNCTION involves_owner_check();

CREATE OR REPLACE FUNCTION involves_one_per_owner_check() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF EXISTS (
            SELECT 1 FROM involves i JOIN vehicle a ON a.vehicle_id=i.vehicle_id
            JOIN vehicle b ON b.vehicle_id=NEW.vehicle_id
            WHERE i.case_id=NEW.case_id AND a.national_id=b.national_id AND i.vehicle_id<>NEW.vehicle_id) THEN RAISE EXCEPTION 'Each party has one vehicle in a case'; END IF; RETURN NEW; END $$;

DROP TRIGGER IF EXISTS involves_one_per_owner ON involves;

CREATE TRIGGER involves_one_per_owner BEFORE INSERT OR UPDATE ON involves FOR EACH ROW EXECUTE FUNCTION involves_one_per_owner_check();

CREATE OR REPLACE FUNCTION receives_participant_check() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NOT EXISTS (
            SELECT 1 FROM final_report f JOIN participates p ON p.case_id=f.case_id
            WHERE f.report_id=NEW.report_id AND p.national_id=NEW.national_id) THEN RAISE EXCEPTION 'Report recipient must participate in the case'; END IF; RETURN NEW; END $$;

DROP TRIGGER IF EXISTS receives_participant ON receives;

CREATE TRIGGER receives_participant BEFORE INSERT OR UPDATE ON receives FOR EACH ROW EXECUTE FUNCTION receives_participant_check();

CREATE OR REPLACE FUNCTION case_submission_check() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.status IN ('pending','in_progress','completed','approved') AND (
        (SELECT count(*) FROM participates WHERE case_id=NEW.case_id)<1 OR
        (SELECT count(*) FROM involves WHERE case_id=NEW.case_id)<1 OR
        (SELECT count(*) FROM dashcam_video WHERE case_id=NEW.case_id)<1 OR
        (NEW.status IN ('in_progress','completed','approved') AND (
            (SELECT count(*) FROM participates WHERE case_id=NEW.case_id)<>2 OR
            (SELECT count(*) FROM involves WHERE case_id=NEW.case_id)<>2))) THEN RAISE EXCEPTION 'Complete the case relationships before submission'; END IF; RETURN NEW; END $$;

DROP TRIGGER IF EXISTS case_submission_check ON accident_case;

CREATE CONSTRAINT TRIGGER case_submission_check AFTER INSERT OR UPDATE ON accident_case DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION case_submission_check();

CREATE OR REPLACE FUNCTION involvement_boxes_check() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE event_key BIGINT; role_key TEXT;
            BEGIN
                IF TG_TABLE_NAME='involvement' THEN event_key:=NEW.event_id; role_key:=NEW.vehicle_role;
                ELSE event_key:=OLD.event_id; role_key:=OLD.vehicle_role; END IF;
                IF EXISTS(SELECT 1 FROM involvement WHERE event_id=event_key AND vehicle_role=role_key)
                    AND NOT EXISTS(SELECT 1 FROM bounding_box WHERE event_id=event_key AND vehicle_role=role_key)
                THEN RAISE EXCEPTION 'Each involvement needs at least one bounding box'; END IF;
                RETURN NULL;
            END $$;

DROP TRIGGER IF EXISTS involvement_boxes_check ON involvement;

CREATE CONSTRAINT TRIGGER involvement_boxes_check AFTER INSERT OR UPDATE ON involvement DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION involvement_boxes_check();

DROP TRIGGER IF EXISTS bounding_box_minimum ON bounding_box;

CREATE CONSTRAINT TRIGGER bounding_box_minimum AFTER DELETE OR UPDATE ON bounding_box DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION involvement_boxes_check();

CREATE OR REPLACE FUNCTION report_recipients_check() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE report_key BIGINT;
            BEGIN
                IF TG_TABLE_NAME='final_report' THEN report_key:=NEW.report_id;
                ELSE report_key:=OLD.report_id; END IF;
                IF EXISTS(SELECT 1 FROM final_report WHERE report_id=report_key)
                    AND NOT EXISTS(SELECT 1 FROM receives WHERE report_id=report_key)
                THEN RAISE EXCEPTION 'Each report needs at least one recipient'; END IF;
                RETURN NULL;
            END $$;

DROP TRIGGER IF EXISTS report_recipients_check ON final_report;

CREATE CONSTRAINT TRIGGER report_recipients_check AFTER INSERT OR UPDATE ON final_report DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION report_recipients_check();

DROP TRIGGER IF EXISTS receives_minimum ON receives;

CREATE CONSTRAINT TRIGGER receives_minimum AFTER DELETE OR UPDATE ON receives DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION report_recipients_check();
