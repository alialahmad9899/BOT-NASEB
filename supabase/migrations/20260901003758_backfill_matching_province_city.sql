update public.profiles
set city = province
where city is null
  and province in ('دمشق','حلب','حمص','حماة','اللاذقية','طرطوس','إدلب','الرقة','دير الزور','الحسكة','درعا','السويداء','القنيطرة');
