--
-- PostgreSQL database dump
--

\restrict ecPdeU7xeSPOIqDXY1OGrUrGl085RWxJDBqhFfNT959XyBnmv8zQLYwjTqeSHXQ

-- Dumped from database version 16.12 (Debian 16.12-1.pgdg13+1)
-- Dumped by pg_dump version 16.12 (Debian 16.12-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
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
-- Name: candidate_sets; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.candidate_sets (
    id integer NOT NULL,
    owner_user_id integer NOT NULL,
    track_code character varying(32) NOT NULL,
    title character varying(255) NOT NULL,
    questions_text text NOT NULL,
    status character varying(32) NOT NULL,
    admin_comment text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.candidate_sets OWNER TO postgres;

--
-- Name: candidate_sets_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.candidate_sets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.candidate_sets_id_seq OWNER TO postgres;

--
-- Name: candidate_sets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.candidate_sets_id_seq OWNED BY public.candidate_sets.id;


--
-- Name: interview_proposals; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.interview_proposals (
    id integer NOT NULL,
    student_id integer NOT NULL,
    interviewer_id integer NOT NULL,
    track_code character varying(32) NOT NULL,
    pack_id integer NOT NULL,
    options_json json NOT NULL,
    status character varying(32) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.interview_proposals OWNER TO postgres;

--
-- Name: interview_proposals_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.interview_proposals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.interview_proposals_id_seq OWNER TO postgres;

--
-- Name: interview_proposals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.interview_proposals_id_seq OWNED BY public.interview_proposals.id;


--
-- Name: interview_tracks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.interview_tracks (
    id integer NOT NULL,
    code character varying(32) NOT NULL,
    title character varying(128) NOT NULL
);


ALTER TABLE public.interview_tracks OWNER TO postgres;

--
-- Name: interview_tracks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.interview_tracks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.interview_tracks_id_seq OWNER TO postgres;

--
-- Name: interview_tracks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.interview_tracks_id_seq OWNED BY public.interview_tracks.id;


--
-- Name: match_requests; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.match_requests (
    id integer NOT NULL,
    requester_id integer NOT NULL,
    mode character varying(32) NOT NULL,
    track_code character varying(32) NOT NULL,
    pack_id integer,
    status character varying(32) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.match_requests OWNER TO postgres;

--
-- Name: match_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.match_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.match_requests_id_seq OWNER TO postgres;

--
-- Name: match_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.match_requests_id_seq OWNED BY public.match_requests.id;


--
-- Name: pack_submissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pack_submissions (
    id integer NOT NULL,
    student_user_id integer NOT NULL,
    content_text text NOT NULL,
    source_message_link text,
    status character varying(32) NOT NULL,
    admin_comment text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.pack_submissions OWNER TO postgres;

--
-- Name: pack_submissions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.pack_submissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pack_submissions_id_seq OWNER TO postgres;

--
-- Name: pack_submissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.pack_submissions_id_seq OWNED BY public.pack_submissions.id;


--
-- Name: pair_stats; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pair_stats (
    id integer NOT NULL,
    user_a_id integer NOT NULL,
    user_b_id integer NOT NULL,
    interviews_count integer NOT NULL,
    last_interview_at timestamp without time zone
);


ALTER TABLE public.pair_stats OWNER TO postgres;

--
-- Name: pair_stats_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.pair_stats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pair_stats_id_seq OWNER TO postgres;

--
-- Name: pair_stats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.pair_stats_id_seq OWNED BY public.pair_stats.id;


--
-- Name: quick_evaluations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.quick_evaluations (
    id integer NOT NULL,
    interviewer_tg_user_id bigint NOT NULL,
    candidate_username character varying(255) NOT NULL,
    set_id integer,
    score integer NOT NULL,
    comment text NOT NULL,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.quick_evaluations OWNER TO postgres;

--
-- Name: quick_evaluations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.quick_evaluations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.quick_evaluations_id_seq OWNER TO postgres;

--
-- Name: quick_evaluations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.quick_evaluations_id_seq OWNED BY public.quick_evaluations.id;


--
-- Name: session_feedback; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.session_feedback (
    id integer NOT NULL,
    session_id integer NOT NULL,
    author_user_id integer NOT NULL,
    about_user_id integer NOT NULL,
    role_context character varying(32) NOT NULL,
    score integer NOT NULL,
    feedback text NOT NULL,
    rubric json,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.session_feedback OWNER TO postgres;

--
-- Name: session_feedback_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.session_feedback_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.session_feedback_id_seq OWNER TO postgres;

--
-- Name: session_feedback_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.session_feedback_id_seq OWNED BY public.session_feedback.id;


--
-- Name: session_reviews; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.session_reviews (
    id integer NOT NULL,
    session_id integer NOT NULL,
    author_user_id integer NOT NULL,
    target_user_id integer NOT NULL,
    author_role character varying(32) NOT NULL,
    score integer NOT NULL,
    comment text NOT NULL,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.session_reviews OWNER TO postgres;

--
-- Name: session_reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.session_reviews_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.session_reviews_id_seq OWNER TO postgres;

--
-- Name: session_reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.session_reviews_id_seq OWNED BY public.session_reviews.id;


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sessions (
    id integer NOT NULL,
    interviewer_id integer NOT NULL,
    student_id integer NOT NULL,
    track_code character varying(32) NOT NULL,
    pack_id integer NOT NULL,
    starts_at timestamp without time zone NOT NULL,
    ends_at timestamp without time zone NOT NULL,
    meeting_url text,
    status character varying(32) NOT NULL,
    reminder_sent boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.sessions OWNER TO postgres;

--
-- Name: sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sessions_id_seq OWNER TO postgres;

--
-- Name: sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sessions_id_seq OWNED BY public.sessions.id;


--
-- Name: task_packs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.task_packs (
    id integer NOT NULL,
    owner_user_id integer NOT NULL,
    track_id integer NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    is_active boolean NOT NULL
);


ALTER TABLE public.task_packs OWNER TO postgres;

--
-- Name: task_packs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.task_packs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.task_packs_id_seq OWNER TO postgres;

--
-- Name: task_packs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.task_packs_id_seq OWNED BY public.task_packs.id;


--
-- Name: tasks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tasks (
    id integer NOT NULL,
    pack_id integer NOT NULL,
    "position" integer NOT NULL,
    question text NOT NULL
);


ALTER TABLE public.tasks OWNER TO postgres;

--
-- Name: tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tasks_id_seq OWNER TO postgres;

--
-- Name: tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.tasks_id_seq OWNED BY public.tasks.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    tg_user_id bigint NOT NULL,
    username character varying(255),
    full_name character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: candidate_sets id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.candidate_sets ALTER COLUMN id SET DEFAULT nextval('public.candidate_sets_id_seq'::regclass);


--
-- Name: interview_proposals id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interview_proposals ALTER COLUMN id SET DEFAULT nextval('public.interview_proposals_id_seq'::regclass);


--
-- Name: interview_tracks id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interview_tracks ALTER COLUMN id SET DEFAULT nextval('public.interview_tracks_id_seq'::regclass);


--
-- Name: match_requests id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.match_requests ALTER COLUMN id SET DEFAULT nextval('public.match_requests_id_seq'::regclass);


--
-- Name: pack_submissions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pack_submissions ALTER COLUMN id SET DEFAULT nextval('public.pack_submissions_id_seq'::regclass);


--
-- Name: pair_stats id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pair_stats ALTER COLUMN id SET DEFAULT nextval('public.pair_stats_id_seq'::regclass);


--
-- Name: quick_evaluations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quick_evaluations ALTER COLUMN id SET DEFAULT nextval('public.quick_evaluations_id_seq'::regclass);


--
-- Name: session_feedback id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_feedback ALTER COLUMN id SET DEFAULT nextval('public.session_feedback_id_seq'::regclass);


--
-- Name: session_reviews id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_reviews ALTER COLUMN id SET DEFAULT nextval('public.session_reviews_id_seq'::regclass);


--
-- Name: sessions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sessions ALTER COLUMN id SET DEFAULT nextval('public.sessions_id_seq'::regclass);


--
-- Name: task_packs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.task_packs ALTER COLUMN id SET DEFAULT nextval('public.task_packs_id_seq'::regclass);


--
-- Name: tasks id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasks ALTER COLUMN id SET DEFAULT nextval('public.tasks_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: candidate_sets; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.candidate_sets (id, owner_user_id, track_code, title, questions_text, status, admin_comment, created_at, updated_at) FROM stdin;
1	1	livecoding	Did	Ddd	approved	Принято	2026-02-23 10:59:24.875835	2026-02-23 10:59:36.061135
2	2	livecoding	ff	ff	approved	Принято	2026-02-23 11:00:05.905493	2026-02-23 11:00:07.467486
\.


--
-- Data for Name: interview_proposals; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.interview_proposals (id, student_id, interviewer_id, track_code, pack_id, options_json, status, created_at) FROM stdin;
1	1	2	livecoding	2	{"request": "Gg", "parsed_slots": [], "final_time": "2026-02-23 14:05"}	accepted	2026-02-23 11:00:17.035387
2	1	2	livecoding	2	{"request": "Ff", "parsed_slots": []}	pending	2026-02-23 11:05:13.557974
3	2	1	livecoding	1	{"request": "2026-02-23 14:25", "parsed_slots": ["2026-02-23 14:25"], "final_time": "2026-02-23 14:25"}	accepted	2026-02-23 11:06:07.857076
4	1	2	livecoding	2	{"request": "D", "parsed_slots": [], "final_time": "2026-02-23 14:25"}	accepted	2026-02-23 11:13:56.235454
5	2	1	livecoding	1	{"request": "2026-02-23 14:33", "parsed_slots": ["2026-02-23 14:33"], "final_time": "2026-02-23 14:33"}	accepted	2026-02-23 11:17:40.646399
\.


--
-- Data for Name: interview_tracks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.interview_tracks (id, code, title) FROM stdin;
\.


--
-- Data for Name: match_requests; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.match_requests (id, requester_id, mode, track_code, pack_id, status, created_at) FROM stdin;
\.


--
-- Data for Name: pack_submissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.pack_submissions (id, student_user_id, content_text, source_message_link, status, admin_comment, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: pair_stats; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.pair_stats (id, user_a_id, user_b_id, interviews_count, last_interview_at) FROM stdin;
1	1	2	4	2026-02-23 11:17:45.288184
\.


--
-- Data for Name: quick_evaluations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.quick_evaluations (id, interviewer_tg_user_id, candidate_username, set_id, score, comment, created_at) FROM stdin;
\.


--
-- Data for Name: session_feedback; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.session_feedback (id, session_id, author_user_id, about_user_id, role_context, score, feedback, rubric, created_at) FROM stdin;
\.


--
-- Data for Name: session_reviews; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.session_reviews (id, session_id, author_user_id, target_user_id, author_role, score, comment, created_at) FROM stdin;
\.


--
-- Data for Name: sessions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sessions (id, interviewer_id, student_id, track_code, pack_id, starts_at, ends_at, meeting_url, status, reminder_sent, created_at) FROM stdin;
1	2	1	livecoding	2	2026-02-23 14:05:00	2026-02-23 15:05:00	https://telemost.yandex.ru/1	scheduled	f	2026-02-23 11:00:37.730964
2	1	2	livecoding	1	2026-02-23 14:25:00	2026-02-23 15:25:00	https://telemost.yandex.ru/3	scheduled	f	2026-02-23 11:06:12.344247
3	2	1	livecoding	2	2026-02-23 14:25:00	2026-02-23 15:25:00	https://telemost.yandex.ru/4	scheduled	f	2026-02-23 11:14:13.726556
4	1	2	livecoding	1	2026-02-23 14:33:00	2026-02-23 15:33:00	https://telemost.yandex.ru/5	scheduled	f	2026-02-23 11:17:45.285127
\.


--
-- Data for Name: task_packs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.task_packs (id, owner_user_id, track_id, title, description, is_active) FROM stdin;
\.


--
-- Data for Name: tasks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.tasks (id, pack_id, "position", question) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, tg_user_id, username, full_name, is_active, created_at) FROM stdin;
1	7927469894	agulyaev_work	Антон Гуляев	t	2026-02-23 10:59:04.480543
2	1019107931	kishmyak	Антон Гуляев	t	2026-02-23 10:59:53.300498
\.


--
-- Name: candidate_sets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.candidate_sets_id_seq', 2, true);


--
-- Name: interview_proposals_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.interview_proposals_id_seq', 5, true);


--
-- Name: interview_tracks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.interview_tracks_id_seq', 1, false);


--
-- Name: match_requests_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.match_requests_id_seq', 1, false);


--
-- Name: pack_submissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.pack_submissions_id_seq', 1, false);


--
-- Name: pair_stats_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.pair_stats_id_seq', 1, true);


--
-- Name: quick_evaluations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.quick_evaluations_id_seq', 1, false);


--
-- Name: session_feedback_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.session_feedback_id_seq', 1, false);


--
-- Name: session_reviews_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.session_reviews_id_seq', 1, false);


--
-- Name: sessions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sessions_id_seq', 4, true);


--
-- Name: task_packs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.task_packs_id_seq', 1, false);


--
-- Name: tasks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.tasks_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 2, true);


--
-- Name: candidate_sets candidate_sets_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.candidate_sets
    ADD CONSTRAINT candidate_sets_pkey PRIMARY KEY (id);


--
-- Name: interview_proposals interview_proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interview_proposals
    ADD CONSTRAINT interview_proposals_pkey PRIMARY KEY (id);


--
-- Name: interview_tracks interview_tracks_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interview_tracks
    ADD CONSTRAINT interview_tracks_code_key UNIQUE (code);


--
-- Name: interview_tracks interview_tracks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interview_tracks
    ADD CONSTRAINT interview_tracks_pkey PRIMARY KEY (id);


--
-- Name: interview_tracks interview_tracks_title_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interview_tracks
    ADD CONSTRAINT interview_tracks_title_key UNIQUE (title);


--
-- Name: match_requests match_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.match_requests
    ADD CONSTRAINT match_requests_pkey PRIMARY KEY (id);


--
-- Name: pack_submissions pack_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pack_submissions
    ADD CONSTRAINT pack_submissions_pkey PRIMARY KEY (id);


--
-- Name: pair_stats pair_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pair_stats
    ADD CONSTRAINT pair_stats_pkey PRIMARY KEY (id);


--
-- Name: quick_evaluations quick_evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quick_evaluations
    ADD CONSTRAINT quick_evaluations_pkey PRIMARY KEY (id);


--
-- Name: session_feedback session_feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_feedback
    ADD CONSTRAINT session_feedback_pkey PRIMARY KEY (id);


--
-- Name: session_reviews session_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_reviews
    ADD CONSTRAINT session_reviews_pkey PRIMARY KEY (id);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: task_packs task_packs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.task_packs
    ADD CONSTRAINT task_packs_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: pair_stats uq_pair; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pair_stats
    ADD CONSTRAINT uq_pair UNIQUE (user_a_id, user_b_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_candidate_sets_owner_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_candidate_sets_owner_user_id ON public.candidate_sets USING btree (owner_user_id);


--
-- Name: ix_candidate_sets_track_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_candidate_sets_track_code ON public.candidate_sets USING btree (track_code);


--
-- Name: ix_interview_proposals_interviewer_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_interview_proposals_interviewer_id ON public.interview_proposals USING btree (interviewer_id);


--
-- Name: ix_interview_proposals_student_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_interview_proposals_student_id ON public.interview_proposals USING btree (student_id);


--
-- Name: ix_pack_submissions_student_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_pack_submissions_student_user_id ON public.pack_submissions USING btree (student_user_id);


--
-- Name: ix_quick_evaluations_interviewer_tg_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_quick_evaluations_interviewer_tg_user_id ON public.quick_evaluations USING btree (interviewer_tg_user_id);


--
-- Name: ix_session_reviews_author_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_session_reviews_author_user_id ON public.session_reviews USING btree (author_user_id);


--
-- Name: ix_session_reviews_session_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_session_reviews_session_id ON public.session_reviews USING btree (session_id);


--
-- Name: ix_session_reviews_target_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_session_reviews_target_user_id ON public.session_reviews USING btree (target_user_id);


--
-- Name: ix_users_tg_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_tg_user_id ON public.users USING btree (tg_user_id);


--
-- Name: candidate_sets candidate_sets_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.candidate_sets
    ADD CONSTRAINT candidate_sets_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public.users(id);


--
-- Name: interview_proposals interview_proposals_interviewer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interview_proposals
    ADD CONSTRAINT interview_proposals_interviewer_id_fkey FOREIGN KEY (interviewer_id) REFERENCES public.users(id);


--
-- Name: interview_proposals interview_proposals_pack_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interview_proposals
    ADD CONSTRAINT interview_proposals_pack_id_fkey FOREIGN KEY (pack_id) REFERENCES public.candidate_sets(id);


--
-- Name: interview_proposals interview_proposals_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interview_proposals
    ADD CONSTRAINT interview_proposals_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.users(id);


--
-- Name: match_requests match_requests_pack_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.match_requests
    ADD CONSTRAINT match_requests_pack_id_fkey FOREIGN KEY (pack_id) REFERENCES public.task_packs(id);


--
-- Name: match_requests match_requests_requester_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.match_requests
    ADD CONSTRAINT match_requests_requester_id_fkey FOREIGN KEY (requester_id) REFERENCES public.users(id);


--
-- Name: pack_submissions pack_submissions_student_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pack_submissions
    ADD CONSTRAINT pack_submissions_student_user_id_fkey FOREIGN KEY (student_user_id) REFERENCES public.users(id);


--
-- Name: pair_stats pair_stats_user_a_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pair_stats
    ADD CONSTRAINT pair_stats_user_a_id_fkey FOREIGN KEY (user_a_id) REFERENCES public.users(id);


--
-- Name: pair_stats pair_stats_user_b_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pair_stats
    ADD CONSTRAINT pair_stats_user_b_id_fkey FOREIGN KEY (user_b_id) REFERENCES public.users(id);


--
-- Name: quick_evaluations quick_evaluations_set_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quick_evaluations
    ADD CONSTRAINT quick_evaluations_set_id_fkey FOREIGN KEY (set_id) REFERENCES public.candidate_sets(id);


--
-- Name: session_feedback session_feedback_about_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_feedback
    ADD CONSTRAINT session_feedback_about_user_id_fkey FOREIGN KEY (about_user_id) REFERENCES public.users(id);


--
-- Name: session_feedback session_feedback_author_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_feedback
    ADD CONSTRAINT session_feedback_author_user_id_fkey FOREIGN KEY (author_user_id) REFERENCES public.users(id);


--
-- Name: session_feedback session_feedback_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_feedback
    ADD CONSTRAINT session_feedback_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.sessions(id);


--
-- Name: session_reviews session_reviews_author_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_reviews
    ADD CONSTRAINT session_reviews_author_user_id_fkey FOREIGN KEY (author_user_id) REFERENCES public.users(id);


--
-- Name: session_reviews session_reviews_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_reviews
    ADD CONSTRAINT session_reviews_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.sessions(id);


--
-- Name: session_reviews session_reviews_target_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.session_reviews
    ADD CONSTRAINT session_reviews_target_user_id_fkey FOREIGN KEY (target_user_id) REFERENCES public.users(id);


--
-- Name: sessions sessions_interviewer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_interviewer_id_fkey FOREIGN KEY (interviewer_id) REFERENCES public.users(id);


--
-- Name: sessions sessions_pack_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pack_id_fkey FOREIGN KEY (pack_id) REFERENCES public.candidate_sets(id);


--
-- Name: sessions sessions_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.users(id);


--
-- Name: task_packs task_packs_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.task_packs
    ADD CONSTRAINT task_packs_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public.users(id);


--
-- Name: task_packs task_packs_track_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.task_packs
    ADD CONSTRAINT task_packs_track_id_fkey FOREIGN KEY (track_id) REFERENCES public.interview_tracks(id);


--
-- Name: tasks tasks_pack_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pack_id_fkey FOREIGN KEY (pack_id) REFERENCES public.task_packs(id);


--
-- PostgreSQL database dump complete
--

\unrestrict ecPdeU7xeSPOIqDXY1OGrUrGl085RWxJDBqhFfNT959XyBnmv8zQLYwjTqeSHXQ

