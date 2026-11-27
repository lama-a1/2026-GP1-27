# vehicle versions (is_current): a submitted case keeps its car exactly as it was,
# while "My vehicles" and later cases use the new details
from test_full_flow import module, app, factory, login_as, post

def car_form(letters, number, model='Camry', year='2023', color='White', vid=''):
    return {'vehicle_id':vid,'plate_letters':letters,'plate_numbers':number,'manufacturer':'Toyota','model':model,'year':year,'color':color}

def submitted_case_with_car():
    with module.conn() as db:
        nid,_=factory.make_party(db,'Car Owner')
        cid=factory.make_case(db,nid,with_vehicles=True)
        db.execute('UPDATE participation_progress SET completed=1 WHERE case_id=?',(cid,))
        car=db.execute('SELECT v.* FROM involves i JOIN vehicle v ON v.vehicle_id=i.vehicle_id WHERE i.case_id=?',(cid,)).fetchone()
    return nid,cid,dict(car)

def my_cars(nid):
    with module.conn() as db:
        return db.execute(module.VEHICLE_SQL+' WHERE national_id=? AND is_current=1',(nid,)).fetchall()

def case_car(cid):
    with module.conn() as db:
        return db.execute('SELECT v.* FROM involves i JOIN vehicle v ON v.vehicle_id=i.vehicle_id WHERE i.case_id=?',(cid,)).fetchone()

def test_new_car_is_current():
    with module.conn() as db:
        nid,_=factory.make_party(db,'New Owner')
    with app.test_client() as c:
        login_as(c,nid)
        post(c,'/profile/vehicles',car_form('أ ب ح','1234'))
    cars=my_cars(nid)
    assert len(cars)==1 and cars[0]['is_current']==1

def test_editing_a_car_of_a_submitted_case_keeps_the_case_unchanged():
    nid,cid,car=submitted_case_with_car()
    with app.test_client() as c:
        login_as(c,nid)
        post(c,'/profile/vehicles',car_form(car['plate_letters'],car['plate_number'],model='Corolla',vid=str(car['vehicle_id'])))
    in_case=case_car(cid)
    assert in_case['vehicle_id']==car['vehicle_id'] and in_case['model']=='Camry' and in_case['is_current']==0
    cars=my_cars(nid)
    assert len(cars)==1 and cars[0]['model']=='Corolla' and cars[0]['vehicle_id']!=car['vehicle_id']

def test_plate_of_a_car_in_a_submitted_case_can_be_changed_and_the_case_keeps_the_old_plate():
    nid,cid,car=submitted_case_with_car()
    with app.test_client() as c:
        login_as(c,nid)
        post(c,'/profile/vehicles',car_form('د ر س','77',vid=str(car['vehicle_id'])))
    assert case_car(cid)['plate_number']==car['plate_number']
    cars=my_cars(nid)
    assert len(cars)==1 and cars[0]['plate_number']=='77' and cars[0]['plate_letters']=='د ر س'

def test_editing_twice_keeps_one_current_row():
    nid,cid,car=submitted_case_with_car()
    with app.test_client() as c:
        login_as(c,nid)
        post(c,'/profile/vehicles',car_form(car['plate_letters'],car['plate_number'],model='Corolla',vid=str(car['vehicle_id'])))
        new_id=my_cars(nid)[0]['vehicle_id']
        post(c,'/profile/vehicles',car_form(car['plate_letters'],car['plate_number'],model='Yaris',vid=str(new_id)))
    cars=my_cars(nid)
    # the second version was in no submitted case, so it was changed in place
    assert len(cars)==1 and cars[0]['vehicle_id']==new_id and cars[0]['model']=='Yaris'
    assert case_car(cid)['model']=='Camry'

def test_an_old_version_cannot_be_edited_directly():
    nid,cid,car=submitted_case_with_car()
    with app.test_client() as c:
        login_as(c,nid)
        post(c,'/profile/vehicles',car_form(car['plate_letters'],car['plate_number'],model='Corolla',vid=str(car['vehicle_id'])))
        post(c,'/profile/vehicles',car_form(car['plate_letters'],car['plate_number'],model='Hacked',vid=str(car['vehicle_id'])))
    assert case_car(cid)['model']=='Camry'
    assert [r['model'] for r in my_cars(nid)]==['Corolla']

def test_new_case_uses_the_edited_details_and_old_case_is_kept():
    nid,cid,car=submitted_case_with_car()
    with module.conn() as db:
        new_cid=factory.make_case(db,nid,progress=2)
    with app.test_client() as c:
        login_as(c,nid)
        post(c,f'/cases/{new_cid}/steps/3',{**car_form(car['plate_letters'],car['plate_number'],model='CX-5'),'garage_id':str(car['vehicle_id'])})
    assert case_car(cid)['model']=='Camry'
    new_case=case_car(new_cid)
    assert new_case and new_case['model']=='CX-5' and new_case['vehicle_id']!=car['vehicle_id']
    assert [r['model'] for r in my_cars(nid)]==['CX-5']

def test_draft_case_moves_to_the_new_details():
    nid,cid,car=submitted_case_with_car()
    with module.conn() as db:
        draft=factory.make_case(db,nid,progress=3)
        db.execute('INSERT INTO involves(case_id,vehicle_id) VALUES(?,?)',(draft,car['vehicle_id']))
    with app.test_client() as c:
        login_as(c,nid)
        post(c,'/profile/vehicles',car_form(car['plate_letters'],car['plate_number'],color='Silver',vid=str(car['vehicle_id'])))
    assert case_car(draft)['color']=='Silver' and case_car(cid)['color']=='White'

def test_car_not_in_a_submitted_case_is_updated_in_place():
    with module.conn() as db:
        nid,_=factory.make_party(db,'Owner')
        vid=factory.add_vehicle(db,nid)
        car=dict(db.execute('SELECT * FROM vehicle WHERE vehicle_id=?',(vid,)).fetchone())
    with app.test_client() as c:
        login_as(c,nid)
        post(c,'/profile/vehicles',car_form(car['plate_letters'],'55',year='2021',vid=str(vid)))
    with module.conn() as db:
        rows=db.execute('SELECT * FROM vehicle WHERE national_id=?',(nid,)).fetchall()
    assert len(rows)==1 and rows[0]['vehicle_id']==vid and rows[0]['year']==2021 and rows[0]['plate_number']=='55'

def test_deleting_a_car_of_a_submitted_case_hides_it_but_keeps_it_for_the_case():
    nid,cid,car=submitted_case_with_car()
    with app.test_client() as c:
        login_as(c,nid)
        post(c,f"/profile/vehicles/{car['vehicle_id']}/delete",{})
    assert my_cars(nid)==[]
    kept=case_car(cid)
    assert kept['vehicle_id']==car['vehicle_id'] and kept['is_current']==0

def test_deleting_a_car_in_a_draft_unlinks_it_and_goes_back_to_the_car_step():
    with module.conn() as db:
        nid,_=factory.make_party(db,'Draft Owner')
        draft=factory.make_case(db,nid,progress=4)
        vid=factory.add_vehicle(db,nid,draft)
    with app.test_client() as c:
        login_as(c,nid)
        post(c,f'/profile/vehicles/{vid}/delete',{})
    with module.conn() as db:
        assert not db.execute('SELECT 1 FROM vehicle WHERE vehicle_id=?',(vid,)).fetchone()
        assert not db.execute('SELECT 1 FROM involves WHERE case_id=?',(draft,)).fetchone()
        assert db.execute('SELECT progress FROM participation_progress WHERE case_id=?',(draft,)).fetchone()['progress']==2

def test_the_plate_of_a_removed_car_can_be_added_again():
    nid,cid,car=submitted_case_with_car()
    with app.test_client() as c:
        login_as(c,nid)
        post(c,f"/profile/vehicles/{car['vehicle_id']}/delete",{})
        post(c,'/profile/vehicles',car_form(car['plate_letters'],car['plate_number'],model='Land Cruiser'))
    cars=my_cars(nid)
    assert len(cars)==1 and cars[0]['model']=='Land Cruiser' and case_car(cid)['model']=='Camry'

def test_duplicate_plate_is_checked_against_current_cars_only():
    nid,cid,car=submitted_case_with_car()
    with module.conn() as db:
        other=factory.add_vehicle(db,nid,number='4321')
    with app.test_client() as c:
        login_as(c,nid)
        # the plate of a current car: refused
        post(c,'/profile/vehicles',car_form(car['plate_letters'],car['plate_number'],vid=str(other)))
    assert sorted(r['plate_number'] for r in my_cars(nid))==sorted([car['plate_number'],'4321'])

def test_old_versions_are_not_listed_in_the_wizard_garage():
    nid,cid,car=submitted_case_with_car()
    with module.conn() as db:
        new_cid=factory.make_case(db,nid,progress=2)
    with app.test_client() as c:
        login_as(c,nid)
        post(c,'/profile/vehicles',car_form(car['plate_letters'],car['plate_number'],model='Corolla',vid=str(car['vehicle_id'])))
        page=c.get(f'/cases/{new_cid}/steps/3').get_data(as_text=True)
    assert 'Corolla' in page and 'Camry' not in page
