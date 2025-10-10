--
-- PostgreSQL database dump
--

\restrict odb8eH9jwdgBNcwZzqxQXXoPpDFPe9oaaf2YT8dPBzSGxUZrkKONKlJfdELkXVB

-- Dumped from database version 17.4 (Postgres.app)
-- Dumped by pg_dump version 17.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: szymonpaluch
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO szymonpaluch;

--
-- Name: audio_stories; Type: TABLE; Schema: public; Owner: szymonpaluch
--

CREATE TABLE public.audio_stories (
    id integer NOT NULL,
    story_id integer NOT NULL,
    voice_id integer NOT NULL,
    user_id integer NOT NULL,
    status character varying(20) NOT NULL,
    error_message text,
    s3_key character varying(512),
    duration_seconds double precision,
    file_size_bytes integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    credits_charged integer
);


ALTER TABLE public.audio_stories OWNER TO szymonpaluch;

--
-- Name: audio_stories_id_seq; Type: SEQUENCE; Schema: public; Owner: szymonpaluch
--

CREATE SEQUENCE public.audio_stories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.audio_stories_id_seq OWNER TO szymonpaluch;

--
-- Name: audio_stories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: szymonpaluch
--

ALTER SEQUENCE public.audio_stories_id_seq OWNED BY public.audio_stories.id;


--
-- Name: credit_lots; Type: TABLE; Schema: public; Owner: szymonpaluch
--

CREATE TABLE public.credit_lots (
    id integer NOT NULL,
    user_id integer NOT NULL,
    source character varying(20) NOT NULL,
    amount_granted integer NOT NULL,
    amount_remaining integer NOT NULL,
    expires_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.credit_lots OWNER TO szymonpaluch;

--
-- Name: credit_lots_id_seq; Type: SEQUENCE; Schema: public; Owner: szymonpaluch
--

CREATE SEQUENCE public.credit_lots_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.credit_lots_id_seq OWNER TO szymonpaluch;

--
-- Name: credit_lots_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: szymonpaluch
--

ALTER SEQUENCE public.credit_lots_id_seq OWNED BY public.credit_lots.id;


--
-- Name: credit_transaction_allocations; Type: TABLE; Schema: public; Owner: szymonpaluch
--

CREATE TABLE public.credit_transaction_allocations (
    transaction_id integer NOT NULL,
    lot_id integer NOT NULL,
    amount integer NOT NULL
);


ALTER TABLE public.credit_transaction_allocations OWNER TO szymonpaluch;

--
-- Name: credit_transactions; Type: TABLE; Schema: public; Owner: szymonpaluch
--

CREATE TABLE public.credit_transactions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    amount integer NOT NULL,
    type character varying(20) NOT NULL,
    reason character varying(255),
    audio_story_id integer,
    story_id integer,
    status character varying(20) DEFAULT 'applied'::character varying NOT NULL,
    metadata json,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.credit_transactions OWNER TO szymonpaluch;

--
-- Name: credit_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: szymonpaluch
--

CREATE SEQUENCE public.credit_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.credit_transactions_id_seq OWNER TO szymonpaluch;

--
-- Name: credit_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: szymonpaluch
--

ALTER SEQUENCE public.credit_transactions_id_seq OWNED BY public.credit_transactions.id;


--
-- Name: stories; Type: TABLE; Schema: public; Owner: szymonpaluch
--

CREATE TABLE public.stories (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    author character varying(255) NOT NULL,
    description text,
    content text NOT NULL,
    cover_filename character varying(255),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    s3_cover_key character varying(512)
);


ALTER TABLE public.stories OWNER TO szymonpaluch;

--
-- Name: stories_id_seq; Type: SEQUENCE; Schema: public; Owner: szymonpaluch
--

CREATE SEQUENCE public.stories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stories_id_seq OWNER TO szymonpaluch;

--
-- Name: stories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: szymonpaluch
--

ALTER SEQUENCE public.stories_id_seq OWNED BY public.stories.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: szymonpaluch
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    email_confirmed boolean,
    is_active boolean,
    last_login timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    is_admin boolean,
    credits_balance integer DEFAULT 0 NOT NULL
);


ALTER TABLE public.users OWNER TO szymonpaluch;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: szymonpaluch
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO szymonpaluch;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: szymonpaluch
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: voices; Type: TABLE; Schema: public; Owner: szymonpaluch
--

CREATE TABLE public.voices (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    elevenlabs_voice_id character varying(255),
    s3_sample_key character varying(512),
    sample_filename character varying(255),
    user_id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    status character varying(20) NOT NULL,
    error_message text
);


ALTER TABLE public.voices OWNER TO szymonpaluch;

--
-- Name: voices_id_seq; Type: SEQUENCE; Schema: public; Owner: szymonpaluch
--

CREATE SEQUENCE public.voices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.voices_id_seq OWNER TO szymonpaluch;

--
-- Name: voices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: szymonpaluch
--

ALTER SEQUENCE public.voices_id_seq OWNED BY public.voices.id;


--
-- Name: audio_stories id; Type: DEFAULT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.audio_stories ALTER COLUMN id SET DEFAULT nextval('public.audio_stories_id_seq'::regclass);


--
-- Name: credit_lots id; Type: DEFAULT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_lots ALTER COLUMN id SET DEFAULT nextval('public.credit_lots_id_seq'::regclass);


--
-- Name: credit_transactions id; Type: DEFAULT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_transactions ALTER COLUMN id SET DEFAULT nextval('public.credit_transactions_id_seq'::regclass);


--
-- Name: stories id; Type: DEFAULT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.stories ALTER COLUMN id SET DEFAULT nextval('public.stories_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: voices id; Type: DEFAULT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.voices ALTER COLUMN id SET DEFAULT nextval('public.voices_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audio_stories audio_stories_pkey; Type: CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.audio_stories
    ADD CONSTRAINT audio_stories_pkey PRIMARY KEY (id);


--
-- Name: credit_lots credit_lots_pkey; Type: CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_lots
    ADD CONSTRAINT credit_lots_pkey PRIMARY KEY (id);


--
-- Name: credit_transactions credit_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_pkey PRIMARY KEY (id);


--
-- Name: credit_transaction_allocations pk_credit_tx_allocations; Type: CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_transaction_allocations
    ADD CONSTRAINT pk_credit_tx_allocations PRIMARY KEY (transaction_id, lot_id);


--
-- Name: stories stories_pkey; Type: CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.stories
    ADD CONSTRAINT stories_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: voices voices_elevenlabs_voice_id_key; Type: CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.voices
    ADD CONSTRAINT voices_elevenlabs_voice_id_key UNIQUE (elevenlabs_voice_id);


--
-- Name: voices voices_pkey; Type: CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.voices
    ADD CONSTRAINT voices_pkey PRIMARY KEY (id);


--
-- Name: ix_credit_lots_user_expires; Type: INDEX; Schema: public; Owner: szymonpaluch
--

CREATE INDEX ix_credit_lots_user_expires ON public.credit_lots USING btree (user_id, expires_at);


--
-- Name: ix_credit_lots_user_id; Type: INDEX; Schema: public; Owner: szymonpaluch
--

CREATE INDEX ix_credit_lots_user_id ON public.credit_lots USING btree (user_id);


--
-- Name: ix_credit_transactions_audio_story_id; Type: INDEX; Schema: public; Owner: szymonpaluch
--

CREATE INDEX ix_credit_transactions_audio_story_id ON public.credit_transactions USING btree (audio_story_id);


--
-- Name: ix_credit_transactions_story_id; Type: INDEX; Schema: public; Owner: szymonpaluch
--

CREATE INDEX ix_credit_transactions_story_id ON public.credit_transactions USING btree (story_id);


--
-- Name: ix_credit_transactions_user_id; Type: INDEX; Schema: public; Owner: szymonpaluch
--

CREATE INDEX ix_credit_transactions_user_id ON public.credit_transactions USING btree (user_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: szymonpaluch
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: uq_credit_tx_open_debit; Type: INDEX; Schema: public; Owner: szymonpaluch
--

CREATE UNIQUE INDEX uq_credit_tx_open_debit ON public.credit_transactions USING btree (audio_story_id, user_id) WHERE (((type)::text = 'debit'::text) AND ((status)::text = 'applied'::text));


--
-- Name: audio_stories audio_stories_story_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.audio_stories
    ADD CONSTRAINT audio_stories_story_id_fkey FOREIGN KEY (story_id) REFERENCES public.stories(id);


--
-- Name: audio_stories audio_stories_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.audio_stories
    ADD CONSTRAINT audio_stories_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: audio_stories audio_stories_voice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.audio_stories
    ADD CONSTRAINT audio_stories_voice_id_fkey FOREIGN KEY (voice_id) REFERENCES public.voices(id);


--
-- Name: credit_lots credit_lots_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_lots
    ADD CONSTRAINT credit_lots_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: credit_transaction_allocations credit_transaction_allocations_lot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_transaction_allocations
    ADD CONSTRAINT credit_transaction_allocations_lot_id_fkey FOREIGN KEY (lot_id) REFERENCES public.credit_lots(id) ON DELETE CASCADE;


--
-- Name: credit_transaction_allocations credit_transaction_allocations_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_transaction_allocations
    ADD CONSTRAINT credit_transaction_allocations_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.credit_transactions(id) ON DELETE CASCADE;


--
-- Name: credit_transactions credit_transactions_audio_story_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_audio_story_id_fkey FOREIGN KEY (audio_story_id) REFERENCES public.audio_stories(id) ON DELETE SET NULL;


--
-- Name: credit_transactions credit_transactions_story_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_story_id_fkey FOREIGN KEY (story_id) REFERENCES public.stories(id) ON DELETE SET NULL;


--
-- Name: credit_transactions credit_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.credit_transactions
    ADD CONSTRAINT credit_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: voices voices_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: szymonpaluch
--

ALTER TABLE ONLY public.voices
    ADD CONSTRAINT voices_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

GRANT ALL ON SCHEMA public TO szymonpaluch;


--
-- PostgreSQL database dump complete
--

\unrestrict odb8eH9jwdgBNcwZzqxQXXoPpDFPe9oaaf2YT8dPBzSGxUZrkKONKlJfdELkXVB

