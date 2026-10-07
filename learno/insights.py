"""Read-only community pagination, notification counts and private weekly statistics."""
from datetime import date, timedelta
import v2

def positive(query,key):
    values=query.get(key)
    if values is None:return None
    if len(values)!=1 or not values[0].isascii() or not values[0].isdigit():
        raise ValueError('Ungültiger Parameter: '+key)
    value=int(values[0])
    if not 1<=value<=1000000000:raise ValueError('Ungültiger Parameter: '+key)
    return value

def feed(db,uid,query):
    filters=query.get('filter',['all'])
    if len(filters)!=1:raise ValueError('Ungültiger Feedfilter.')
    posts,comments=v2.posts_for(db,uid,filters[0],positive(query,'group_id'),positive(query,'before_id'),51)
    has_more=len(posts)>50;posts=posts[:50];ids={p['id'] for p in posts}
    return {'posts':posts,'comments':[c for c in comments if c['post_id'] in ids],
            'has_more':has_more,'next_before_id':posts[-1]['id'] if has_more else None}

def notices(db,uid,query):
    before=positive(query,'before_id');args=[uid]
    sql='SELECT * FROM notices WHERE user_id=? AND read_at IS NULL'
    if before is not None:sql+=' AND id<?';args.append(before)
    items=v2.rows(db,sql+' ORDER BY id DESC LIMIT 51',args)
    has_more=len(items)>50;items=items[:50]
    return {'notices':items,'notice_count':db.execute('SELECT COUNT(*) FROM notices WHERE user_id=? AND read_at IS NULL',(uid,)).fetchone()[0],
            'has_more':has_more,'next_before_id':items[-1]['id'] if has_more else None}

def statistics(db,uid,today=None):
    today=today or date.today();monday=today-timedelta(days=today.weekday())
    def total(start,end):
        return db.execute('SELECT COALESCE(SUM(seconds),0) FROM sessions WHERE user_id=? AND date>=? AND date<=?',
                          (uid,start.isoformat(),end.isoformat())).fetchone()[0]
    weeks=[]
    for offset in range(5,-1,-1):
        start=monday-timedelta(weeks=offset);end=today if offset==0 else start+timedelta(days=6)
        weeks.append({'week_start':start.isoformat(),'seconds':total(start,end),'current':offset==0})
    goal=db.execute('SELECT weekly_goal_minutes FROM users WHERE id=?',(uid,)).fetchone()[0]
    current=weeks[-1]['seconds'];previous=total(monday-timedelta(days=7),today-timedelta(days=7))
    return {'today':today.isoformat(),'week_start':monday.isoformat(),'weeks':weeks,
            'weekly_goal_minutes':goal,'current_seconds':current,'previous_comparable_seconds':previous,
            'difference_seconds':current-previous,'remaining_seconds':max(0,goal*60-current) if goal is not None else None,
            'goal_percent':min(100,current/(goal*60)*100) if goal is not None else None}
