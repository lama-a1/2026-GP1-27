# small helpers that add test data to the EER tables
import random, uuid
import app as module

def new_national_id():
    return '1'+str(random.randrange(10**8,10**9))

def make_party(db, name='Test Party', notify=1, email=None, national_id=None):
    # add an accident party (ACCIDENT_PARTY) and return its national ID and email
    nid=national_id or new_national_id()
    email=email or name.replace(' ','').lower()+uuid.uuid4().hex[:8]+'@example.test'
    db.execute('''INSERT INTO accident_party(national_id,full_name,date_of_birth,phone,email,password_hash,notify_status_change)
                  VALUES(?,?,?,?,?,?,?)''',(nid,name,'2000-01-01','05'+str(random.randrange(10**7,10**8)),email,'hash',notify))
    return nid,email

def make_case(db, a_nid, b_nid=None, accident_type='REAR_END', progress=0, with_vehicles=False, case_id=None):
    # add a case with party A (and B if given) and return its case ID
    case_id=case_id or 'TEST-'+uuid.uuid4().hex[:10]
    db.execute('INSERT INTO accident_case(case_id,accident_type,accident_date,accident_time,location) VALUES(?,?,?,?,?)',
               (case_id,accident_type,'2026-10-22','10:00','Riyadh'))
    for nid,position in ((a_nid,'A'),(b_nid,'B')):
        if not nid: continue
        db.execute('INSERT INTO participates(national_id,case_id) VALUES(?,?)',(nid,case_id))
        db.execute('INSERT INTO participation_progress(national_id,case_id,position,progress) VALUES(?,?,?,?)',(nid,case_id,position,progress))
        if with_vehicles: add_vehicle(db,nid,case_id)
    return case_id

def add_vehicle(db, nid, case_id=None, letters='أ ب ح', number=None):
    # add a car to the party's "My vehicles" and link it to the case
    number=number or str(random.randrange(1000,9999))
    vid=module.insert_id(db,'INSERT INTO vehicle(plate_letters,plate_number,manufacturer,model,year,color,national_id) VALUES(?,?,?,?,?,?,?)',
                         (letters,number,'Toyota','Camry',2023,'White',nid),'vehicle_id')
    if case_id: db.execute('INSERT INTO involves(case_id,vehicle_id) VALUES(?,?)',(case_id,vid))
    return vid

def add_video(db, case_id, nid, stored, processed=None, camera='front', name='test.mp4'):
    vid=module.add_video(db,case_id,nid,stored,camera,name)
    if processed: db.execute('UPDATE video_processing SET processed_path=? WHERE video_id=?',(processed,vid))
    return vid
