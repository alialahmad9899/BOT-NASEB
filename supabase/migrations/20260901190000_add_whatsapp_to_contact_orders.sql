alter table public.orders
    add column if not exists whatsapp varchar(120);

create index if not exists idx_orders_whatsapp
    on public.orders (whatsapp);
