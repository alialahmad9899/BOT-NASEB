alter table public.profiles
  add column if not exists children_count integer,
  add column if not exists education varchar(200),
  add column if not exists nationality varchar(100),
  add column if not exists religion varchar(100),
  add column if not exists appearance text;

alter table public.profiles
  drop constraint if exists ck_profile_children_count_nonnegative;

alter table public.profiles
  add constraint ck_profile_children_count_nonnegative
  check (children_count is null or children_count >= 0);
