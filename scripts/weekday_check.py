import datetime

d = datetime.date(2026,7,2)
print(d, 'weekday_index=', d.weekday())
names = ['Dushanba','Seshanba','Chorshanba','Payshanba','Juma','Shanba','Yakshanba']
print('name:', names[d.weekday()])
