# blur faces in a local video (plates are not blurred, and the result needs a manual check)
from pathlib import Path
import uuid

def process_privacy(path,folder):
    try:
        import cv2
    except ImportError:
        return {'status':'requires_review','note':'OpenCV غير مثبت. ثبّتي requirements-privacy.txt للمحاولة.'}
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened():return {'status':'requires_review','note':'تعذّر قراءة الفيديو. يلزم فحصه يدوياً.'}
    fps=cap.get(cv2.CAP_PROP_FPS) or 25
    w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not w or not h:cap.release();return {'status':'requires_review','note':'تعذّر تحديد أبعاد الفيديو.'}
    # use the face detector that comes with OpenCV
    face=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    output=uuid.uuid4().hex+'_faces_blurred.mp4'
    writer=cv2.VideoWriter(str(Path(folder)/output),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h))
    if not writer.isOpened():cap.release();return {'status':'requires_review','note':'تعذّر إنشاء نسخة الفيديو المعالجة.'}
    count=0
    # go through the frames and blur the faces we find
    while True:
        ok,frame=cap.read()
        if not ok:break
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        for x,y,fw,fh in face.detectMultiScale(gray,scaleFactor=1.12,minNeighbors=5,minSize=(24,24)):
            roi=frame[y:y+fh,x:x+fw]
            if roi.size:frame[y:y+fh,x:x+fw]=cv2.GaussianBlur(roi,(51,51),25)
        writer.write(frame);count+=1
    cap.release();writer.release()
    if count==0:
        (Path(folder)/output).unlink(missing_ok=True)
        return {'status':'requires_review','note':'الفيديو فارغ أو غير قابل للقراءة.'}
    # keep the result marked for review because some faces may be missed
    return {'filename':output,'status':'requires_review','note':'تمت محاولة طمس الوجوه. يجب مراجعة الفيديو يدوياً؛ اللوحات والوجوه غير المكتشفة لم تُضمن تغطيتها، ولا تشاركي الملف قبل المراجعة.'}
