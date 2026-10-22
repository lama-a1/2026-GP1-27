# check plate letters with and without spaces and keep the three-letter limit
import uuid
import app as module


def test_plate_letters_accept_compact_and_spaced_input():
    for value in ['bjd', 'b j d', 'b jd', 'بحد', 'ب ح د', 'ب حد']:
        assert module.parse_plate(value, '1234') == ('ب ح د 1234', None)
    for value in ['bj', 'b j', 'بح', 'ب ح']:
        assert module.parse_plate(value, '1234') == ('ب ح 1234', None)
    for value in ['hh', 'h h', 'هه', 'هـ هـ']:
        assert module.parse_plate(value, '1234') == ('هـ هـ 1234', None)


def test_plate_rejects_more_than_three_letters():
    for value in ['bjds', 'b j d s', 'بحدس', 'ب ح د س']:
        plate, error = module.parse_plate(value, '1234')
        assert plate is None and error
    assert module.parse_plate('q', '1234')[1]


def test_compact_plate_is_saved_in_the_account():
    tag = uuid.uuid4().hex
    with module.conn() as db:
        uid = module.insert_id(db, 'INSERT INTO users(full_name,email,password_hash,national_id) VALUES(?,?,?,?)',
                               ('Test Plate Owner', tag + '@example.test', 'hash', '1' + str(uuid.uuid4().int)[:9]))
    with module.app.test_client() as client:
        with client.session_transaction() as session:
            session['uid'] = uid
            session['csrf'] = 'plate-check'
        data = {'csrf_token': 'plate-check', 'plate_letters': 'bjd', 'plate_numbers': '1234',
                'manufacturer': 'Toyota', 'model': 'Camry', 'year': '2023', 'color': 'White'}
        assert client.post('/profile/vehicles', data=data).status_code == 302
        with module.conn() as db:
            assert db.execute('SELECT plate FROM garage_vehicles WHERE user_id=?', (uid,)).fetchone()['plate'] == 'ب ح د 1234'
