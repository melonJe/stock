CREATE TABLE public.blacklist (
	symbol varchar NOT NULL,
	record_date date DEFAULT CURRENT_DATE NULL,
	CONSTRAINT blacklist_pkey PRIMARY KEY (symbol)
);

CREATE TABLE public.price_history (
	symbol varchar NOT NULL,
	"date" date NOT NULL,
	"open" int8 NOT NULL,
	high int8 NOT NULL,
	"close" int8 NOT NULL,
	low int8 NOT NULL,
	volume int8 NOT NULL,
	CONSTRAINT price_history_pkey PRIMARY KEY (symbol, date)
);

CREATE TABLE public.price_history_us (
	symbol varchar NOT NULL,
	"date" date NOT NULL,
	"open" numeric(20, 4) NULL,
	high numeric(20, 4) NULL,
	"close" numeric(20, 4) NULL,
	low numeric(20, 4) NULL,
	volume int8 NULL,
	CONSTRAINT price_history_us_pkey PRIMARY KEY (symbol, date)
);

CREATE TABLE public.sell_queue (
	id bigserial NOT NULL,
	symbol varchar NOT NULL,
	volume int4 NOT NULL,
	price numeric(20, 4) NULL,
	CONSTRAINT sell_queue_pkey PRIMARY KEY (id)
);

CREATE TABLE public.stock (
	symbol varchar NOT NULL,
	company_name varchar NOT NULL,
	country varchar NULL,
	CONSTRAINT stock_pkey PRIMARY KEY (symbol)
);

CREATE TABLE public.stop_loss (
	symbol varchar NOT NULL,
	price int4 NOT NULL,
	CONSTRAINT stop_loss_pkey PRIMARY KEY (symbol)
);

CREATE TABLE public."subscription" (
	id bigserial NOT NULL,
	symbol varchar NOT NULL,
	CONSTRAINT subscription_pkey PRIMARY KEY (id),
	CONSTRAINT subscription_unique UNIQUE (symbol)
);