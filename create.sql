CREATE TABLE account (
    email VARCHAR(320) PRIMARY KEY,
    pass_hash BYTEA NOT NULL,
    pass_salt BYTEA NOT NULL
);

CREATE TABLE blacklist (
    symbol VARCHAR PRIMARY KEY,
    record_date DATE DEFAULT CURRENT_DATE
);

CREATE TABLE stock (
    symbol VARCHAR PRIMARY KEY,
    company_name VARCHAR NOT NULL,
    country VARCHAR NULL
);

CREATE TABLE stop_loss (
    symbol VARCHAR PRIMARY KEY,
    price INTEGER NOT NULL
);

CREATE TABLE price_history (
    symbol VARCHAR NOT NULL,
    date DATE NOT NULL,
    open INTEGER NOT NULL,
    high INTEGER NOT NULL,
    close INTEGER NOT NULL,
    low INTEGER NOT NULL,
    volume INTEGER NOT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE price_history_us (
    symbol VARCHAR NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10, 4) NULL,
    high DECIMAL(10, 4) NULL,
    close DECIMAL(10, 4) NULL,
    low DECIMAL(10, 4) NULL,
    volume BIGINT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE sell_queue (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    symbol VARCHAR NOT NULL,
    volume INTEGER NOT NULL,
    price INTEGER NOT NULL
);

CREATE TABLE subscription (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    symbol VARCHAR NOT NULL,
    UNIQUE (email, symbol)
);
