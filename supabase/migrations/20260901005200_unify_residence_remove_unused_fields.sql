alter table public.profiles add column if not exists residence varchar(200);

update public.profiles
set residence = case
    when city is null or btrim(city) = '' or city = province then province
    else province || ' - ' || city
end
where residence is null;

alter table public.profiles alter column residence set not null;

alter table public.profiles drop constraint if exists profiles_status_check;
alter table public.profiles
    add constraint profiles_status_check
    check (status in ('active', 'reserved', 'inactive'));

alter table public.profiles drop column if exists province;
alter table public.profiles drop column if exists city;
alter table public.profiles drop column if exists nationality;
alter table public.profiles drop column if exists religion;
alter table public.profiles drop column if exists description;

create index if not exists ix_profiles_residence on public.profiles (residence);
