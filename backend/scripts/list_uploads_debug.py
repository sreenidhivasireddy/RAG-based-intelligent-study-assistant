from app.database import SessionLocal
from app.repositories.upload_repository import get_all_file_uploads

db = SessionLocal()
uploads = get_all_file_uploads(db=db, skip=0, limit=1000)
for u in uploads:
    print(u.file_md5, '->', repr(u.file_name), 'size=', getattr(u,'total_size',None), 'status=', getattr(u,'status',None))

print('Total:', len(uploads))
db.close()
