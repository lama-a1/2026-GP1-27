# tables and relationships from the Siyaq EER, plus the supporting tables the website needs
from pathlib import Path

ENTITY_TABLES = {'accident_party', 'authorized_expert', 'vehicle', 'accident_case',
                 'dashcam_video', 'detected_event', 'detected_vehicle', 'final_report'}
RELATION_TABLES = {'participates', 'involves', 'involvement', 'bounding_box', 'receives'}
TABLES = ENTITY_TABLES | RELATION_TABLES
# not in the EER: the website needs them to run (invitation links, password reset links,
# login lockout, each party's step in a case, and the video processing state)
SUPPORT_TABLES = {'participation_progress', 'case_invitation', 'password_reset_link',
                  'login_attempt', 'video_processing'}
# tables from the old design (before matching the EER)
LEGACY_TABLES = {'users', 'cases', 'parties', 'vehicles', 'videos', 'invitations',
                 'garage_vehicles', 'analysis_jobs', 'expert_accounts', 'expert_logins',
                 'login_failures', 'password_resets'}


def statements(postgres=False):
    identity = 'BIGSERIAL PRIMARY KEY' if postgres else 'INTEGER PRIMARY KEY'
    number = 'DOUBLE PRECISION' if postgres else 'REAL'
    now = "to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS')" if postgres else 'CURRENT_TIMESTAMP'
    return [
        '''CREATE TABLE IF NOT EXISTS accident_party (
            national_id TEXT PRIMARY KEY NOT NULL, full_name TEXT NOT NULL, date_of_birth TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            notify_status_change INTEGER NOT NULL DEFAULT 1 CHECK (notify_status_change IN (0,1)),
            notify_final_result INTEGER NOT NULL DEFAULT 1 CHECK (notify_final_result IN (0,1)))''',
        f'''CREATE TABLE IF NOT EXISTS authorized_expert (
            expert_id {identity}, full_name TEXT NOT NULL, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL)''',
        f'''CREATE TABLE IF NOT EXISTS vehicle (
            vehicle_id {identity}, plate_number TEXT NOT NULL CHECK (length(plate_number) BETWEEN 1 AND 4),
            plate_letters TEXT NOT NULL CHECK (length(plate_letters) BETWEEN 1 AND 8),
            manufacturer TEXT NOT NULL, model TEXT NOT NULL, year INTEGER NOT NULL, color TEXT NOT NULL,
            national_id TEXT NOT NULL REFERENCES accident_party(national_id))''',
        '''CREATE TABLE IF NOT EXISTS accident_case (
            case_id TEXT PRIMARY KEY NOT NULL, party_b_email TEXT, accident_type TEXT NOT NULL
                CHECK (accident_type IN ('REAR_END','LANE_CHANGE')),
            party_a_position TEXT CHECK (party_a_position IN ('FRONT','REAR')),
            accident_date TEXT NOT NULL, accident_time TEXT NOT NULL, location TEXT NOT NULL,
            party_a_description TEXT, party_b_description TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            reviewed_by_expert_id BIGINT REFERENCES authorized_expert(expert_id))''',
        '''CREATE TABLE IF NOT EXISTS participates (
            national_id TEXT NOT NULL REFERENCES accident_party(national_id),
            case_id TEXT NOT NULL REFERENCES accident_case(case_id) ON DELETE CASCADE,
            PRIMARY KEY (national_id,case_id))''',
        '''CREATE TABLE IF NOT EXISTS involves (
            case_id TEXT NOT NULL REFERENCES accident_case(case_id) ON DELETE CASCADE,
            vehicle_id BIGINT NOT NULL REFERENCES vehicle(vehicle_id),
            PRIMARY KEY (case_id,vehicle_id))''',
        f'''CREATE TABLE IF NOT EXISTS dashcam_video (
            video_id {identity}, storage_path TEXT NOT NULL UNIQUE,
            camera_type TEXT NOT NULL CHECK (camera_type IN ('front','rear')),
            uploaded_at TEXT NOT NULL DEFAULT ({now}), case_id TEXT NOT NULL,
            national_id TEXT NOT NULL, UNIQUE (case_id,national_id),
            FOREIGN KEY (national_id,case_id) REFERENCES participates(national_id,case_id) ON DELETE CASCADE)''',
        f'''CREATE TABLE IF NOT EXISTS detected_event (
            event_id {identity}, event_type TEXT NOT NULL, event_value TEXT, frame_path TEXT,
            start_time {number} NOT NULL, end_time {number} NOT NULL CHECK (end_time >= start_time),
            video_id BIGINT NOT NULL REFERENCES dashcam_video(video_id) ON DELETE CASCADE)''',
        f'''CREATE TABLE IF NOT EXISTS detected_vehicle (
            detected_vehicle_id {identity}, vehicle_id BIGINT REFERENCES vehicle(vehicle_id))''',
        '''CREATE TABLE IF NOT EXISTS involvement (
            event_id BIGINT NOT NULL REFERENCES detected_event(event_id) ON DELETE CASCADE,
            detected_vehicle_id BIGINT NOT NULL REFERENCES detected_vehicle(detected_vehicle_id),
            vehicle_role TEXT NOT NULL, track_id TEXT NOT NULL,
            PRIMARY KEY (event_id,vehicle_role), UNIQUE (event_id,detected_vehicle_id))''',
        '''CREATE TABLE IF NOT EXISTS bounding_box (
            event_id BIGINT NOT NULL, vehicle_role TEXT NOT NULL, bounding_box TEXT NOT NULL,
            PRIMARY KEY (event_id,vehicle_role,bounding_box),
            FOREIGN KEY (event_id,vehicle_role) REFERENCES involvement(event_id,vehicle_role) ON DELETE CASCADE)''',
        f'''CREATE TABLE IF NOT EXISTS final_report (
            report_id {identity}, outcome TEXT, suggested_party_a_fault {number},
            suggested_party_b_fault {number}, party_a_fault {number}, party_b_fault {number},
            undetermined_code TEXT, applied_rule TEXT, expert_notes TEXT, final_description TEXT,
            approved_at TEXT, case_id TEXT NOT NULL UNIQUE REFERENCES accident_case(case_id) ON DELETE CASCADE,
            approved_by_expert_id BIGINT REFERENCES authorized_expert(expert_id))''',
        '''CREATE TABLE IF NOT EXISTS receives (
            report_id BIGINT NOT NULL REFERENCES final_report(report_id) ON DELETE CASCADE,
            national_id TEXT NOT NULL REFERENCES accident_party(national_id),
            PRIMARY KEY (report_id,national_id))''',
        # supporting tables (not in the EER)
        f'''CREATE TABLE IF NOT EXISTS participation_progress (
            national_id TEXT NOT NULL, case_id TEXT NOT NULL,
            position TEXT NOT NULL CHECK (position IN ('A','B')),
            progress INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0,1)),
            description_meta TEXT, joined_at TEXT NOT NULL DEFAULT ({now}),
            PRIMARY KEY (national_id,case_id), UNIQUE (case_id,position),
            FOREIGN KEY (national_id,case_id) REFERENCES participates(national_id,case_id) ON DELETE CASCADE)''',
        f'''CREATE TABLE IF NOT EXISTS case_invitation (
            invitation_id {identity}, case_id TEXT NOT NULL REFERENCES accident_case(case_id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE, recipient_email TEXT NOT NULL, expires_at TEXT NOT NULL,
            claimed_by TEXT REFERENCES accident_party(national_id), revoked_at TEXT,
            created_at TEXT NOT NULL DEFAULT ({now}))''',
        f'''CREATE TABLE IF NOT EXISTS password_reset_link (
            link_id {identity}, national_id TEXT NOT NULL REFERENCES accident_party(national_id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE, expires_at {number} NOT NULL, used_at TEXT)''',
        f'''CREATE TABLE IF NOT EXISTS login_attempt (
            key TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, locked_until {number})''',
        f'''CREATE TABLE IF NOT EXISTS video_processing (
            video_id BIGINT PRIMARY KEY REFERENCES dashcam_video(video_id) ON DELETE CASCADE,
            original_name TEXT NOT NULL, processed_path TEXT,
            privacy_status TEXT NOT NULL DEFAULT 'pending', note TEXT,
            job_status TEXT NOT NULL DEFAULT 'queued', job_details TEXT,
            updated_at TEXT NOT NULL DEFAULT ({now}))''',
        'CREATE INDEX IF NOT EXISTS participates_case_idx ON participates(case_id)',
        'CREATE INDEX IF NOT EXISTS vehicle_owner_idx ON vehicle(national_id)',
        'CREATE INDEX IF NOT EXISTS dashcam_case_idx ON dashcam_video(case_id)',
    ] + relationship_guards(postgres)


def relationship_guards(postgres):
    # check the limits on the relationships as records are added
    rules = [
        ('participates', 'case_id', 'SELECT count(*) FROM participates WHERE case_id=NEW.case_id',
         'A case can have at most two accident parties'),
        ('involves', 'case_id,vehicle_id', 'SELECT count(*) FROM involves WHERE case_id=NEW.case_id',
         'A case can involve at most two vehicles'),
        ('involvement', 'event_id', 'SELECT count(*) FROM involvement WHERE event_id=NEW.event_id',
         'An event can involve at most two detected vehicles'),
        ('receives', 'report_id', 'SELECT count(*) FROM receives WHERE report_id=NEW.report_id',
         'A report can have at most two recipients'),
    ]
    result = []
    for table, columns, count_sql, message in rules:
        name = table + '_max_two'
        if postgres:
            result += [f'''CREATE OR REPLACE FUNCTION {name}_check() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF TG_OP='UPDATE' AND OLD.{columns.split(',')[0]}=NEW.{columns.split(',')[0]} THEN RETURN NEW; END IF;
                    PERFORM 1 FROM {'detected_event' if table == 'involvement' else 'final_report' if table == 'receives' else 'accident_case'}
                    WHERE {'event_id' if table == 'involvement' else 'report_id' if table == 'receives' else 'case_id'} = NEW.{columns.split(',')[0]} FOR UPDATE;
                    IF ({count_sql}) >= 2 THEN RAISE EXCEPTION '{message}'; END IF;
                    RETURN NEW;
                END $$''',
                f'DROP TRIGGER IF EXISTS {name} ON {table}',
                f'CREATE TRIGGER {name} BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION {name}_check()']
        else:
            result.append(f'''CREATE TRIGGER IF NOT EXISTS {name} BEFORE INSERT ON {table}
                WHEN ({count_sql}) >= 2 BEGIN SELECT RAISE(ABORT,'{message}'); END''')
            result.append(f'''CREATE TRIGGER IF NOT EXISTS {name}_update BEFORE UPDATE ON {table}
                WHEN OLD.{columns.split(',')[0]}<>NEW.{columns.split(',')[0]} AND ({count_sql}) >= 2
                BEGIN SELECT RAISE(ABORT,'{message}'); END''')
    checks = [
        ('involves_owner', 'involves', '''NOT EXISTS (
            SELECT 1 FROM vehicle v JOIN participates p ON p.national_id=v.national_id
            WHERE v.vehicle_id=NEW.vehicle_id AND p.case_id=NEW.case_id)''', 'Vehicle owner must participate in this case'),
        ('involves_one_per_owner', 'involves', '''EXISTS (
            SELECT 1 FROM involves i JOIN vehicle a ON a.vehicle_id=i.vehicle_id
            JOIN vehicle b ON b.vehicle_id=NEW.vehicle_id
            WHERE i.case_id=NEW.case_id AND a.national_id=b.national_id AND i.vehicle_id<>NEW.vehicle_id)''', 'Each party has one vehicle in a case'),
        ('receives_participant', 'receives', '''NOT EXISTS (
            SELECT 1 FROM final_report f JOIN participates p ON p.case_id=f.case_id
            WHERE f.report_id=NEW.report_id AND p.national_id=NEW.national_id)''', 'Report recipient must participate in the case'),
    ]
    for name, table, condition, message in checks:
        if postgres:
            result += [f'''CREATE OR REPLACE FUNCTION {name}_check() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF {condition} THEN RAISE EXCEPTION '{message}'; END IF; RETURN NEW; END $$''',
                f'DROP TRIGGER IF EXISTS {name} ON {table}',
                f'CREATE TRIGGER {name} BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION {name}_check()']
        else:
            result.append(f'''CREATE TRIGGER IF NOT EXISTS {name} BEFORE INSERT ON {table}
                WHEN {condition} BEGIN SELECT RAISE(ABORT,'{message}'); END''')
            result.append(f'''CREATE TRIGGER IF NOT EXISTS {name}_update BEFORE UPDATE ON {table}
                WHEN {condition} BEGIN SELECT RAISE(ABORT,'{message}'); END''')
    return result + submission_guard(postgres)


def submission_guard(postgres):
    condition = """NEW.status IN ('pending','in_progress','completed','approved') AND (
        (SELECT count(*) FROM participates WHERE case_id=NEW.case_id)<1 OR
        (SELECT count(*) FROM involves WHERE case_id=NEW.case_id)<1 OR
        (SELECT count(*) FROM dashcam_video WHERE case_id=NEW.case_id)<1 OR
        (NEW.status IN ('in_progress','completed','approved') AND (
            (SELECT count(*) FROM participates WHERE case_id=NEW.case_id)<>2 OR
            (SELECT count(*) FROM involves WHERE case_id=NEW.case_id)<>2)))"""
    if not postgres:
        return [f"""CREATE TRIGGER IF NOT EXISTS case_submission_check BEFORE UPDATE OF status ON accident_case
            WHEN {condition} BEGIN SELECT RAISE(ABORT,'Complete the case relationships before submission'); END"""]
    return [f"""CREATE OR REPLACE FUNCTION case_submission_check() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF {condition} THEN RAISE EXCEPTION 'Complete the case relationships before submission'; END IF; RETURN NEW; END $$""",
        'DROP TRIGGER IF EXISTS case_submission_check ON accident_case',
        'CREATE CONSTRAINT TRIGGER case_submission_check AFTER INSERT OR UPDATE ON accident_case DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION case_submission_check()',
        """CREATE OR REPLACE FUNCTION involvement_boxes_check() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE event_key BIGINT; role_key TEXT;
            BEGIN
                IF TG_TABLE_NAME='involvement' THEN event_key:=NEW.event_id; role_key:=NEW.vehicle_role;
                ELSE event_key:=OLD.event_id; role_key:=OLD.vehicle_role; END IF;
                IF EXISTS(SELECT 1 FROM involvement WHERE event_id=event_key AND vehicle_role=role_key)
                    AND NOT EXISTS(SELECT 1 FROM bounding_box WHERE event_id=event_key AND vehicle_role=role_key)
                THEN RAISE EXCEPTION 'Each involvement needs at least one bounding box'; END IF;
                RETURN NULL;
            END $$""",
        'DROP TRIGGER IF EXISTS involvement_boxes_check ON involvement',
        'CREATE CONSTRAINT TRIGGER involvement_boxes_check AFTER INSERT OR UPDATE ON involvement DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION involvement_boxes_check()',
        'DROP TRIGGER IF EXISTS bounding_box_minimum ON bounding_box',
        'CREATE CONSTRAINT TRIGGER bounding_box_minimum AFTER DELETE OR UPDATE ON bounding_box DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION involvement_boxes_check()',
        """CREATE OR REPLACE FUNCTION report_recipients_check() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE report_key BIGINT;
            BEGIN
                IF TG_TABLE_NAME='final_report' THEN report_key:=NEW.report_id;
                ELSE report_key:=OLD.report_id; END IF;
                IF EXISTS(SELECT 1 FROM final_report WHERE report_id=report_key)
                    AND NOT EXISTS(SELECT 1 FROM receives WHERE report_id=report_key)
                THEN RAISE EXCEPTION 'Each report needs at least one recipient'; END IF;
                RETURN NULL;
            END $$""",
        'DROP TRIGGER IF EXISTS report_recipients_check ON final_report',
        'CREATE CONSTRAINT TRIGGER report_recipients_check AFTER INSERT OR UPDATE ON final_report DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION report_recipients_check()',
        'DROP TRIGGER IF EXISTS receives_minimum ON receives',
        'CREATE CONSTRAINT TRIGGER receives_minimum AFTER DELETE OR UPDATE ON receives DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION report_recipients_check()',
    ]


def write_sql(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for postgres, name in [(True,'postgresql.sql'),(False,'sqlite.sql')]:
        (folder/name).write_text('-- Siyaq EER schema\n\n'+';\n\n'.join(statements(postgres))+';\n')


if __name__ == '__main__':
    write_sql(Path(__file__).parent/'database')
