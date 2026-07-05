-- ============================================================================
-- TripPilot — Supabase Database Migrations
-- Run this SQL in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)
-- ============================================================================

-- 1. User Profiles
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name       TEXT DEFAULT '',
    phone_number    TEXT DEFAULT '',
    birth_date      DATE,
    travel_preferences JSONB DEFAULT '{}'::jsonb,
    telegram_chat_id TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Auto-create a profile row when a new user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (id, full_name)
    VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data ->> 'full_name', ''))
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 2. Bookings
CREATE TABLE IF NOT EXISTS public.bookings (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    booking_type                TEXT NOT NULL CHECK (booking_type IN ('flight', 'train', 'hotel')),
    provider_name               TEXT DEFAULT '',
    pnr_or_confirmation_number  TEXT NOT NULL,
    booking_date                TIMESTAMPTZ DEFAULT now(),
    travel_date                 DATE,
    details                     JSONB DEFAULT '{}'::jsonb,
    status                      TEXT DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled', 'completed')),
    created_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON public.bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_travel_date ON public.bookings(travel_date);

-- 3. Row Level Security
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;

-- Profiles: users can only read/write their own profile
CREATE POLICY "Users can view own profile"
    ON public.user_profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON public.user_profiles FOR UPDATE
    USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile"
    ON public.user_profiles FOR INSERT
    WITH CHECK (auth.uid() = id);

-- Bookings: users can only read/write their own bookings
CREATE POLICY "Users can view own bookings"
    ON public.bookings FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own bookings"
    ON public.bookings FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own bookings"
    ON public.bookings FOR UPDATE
    USING (auth.uid() = user_id);

-- 4. Auto-update updated_at on profile changes
CREATE OR REPLACE FUNCTION public.update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_user_profiles_modtime ON public.user_profiles;
CREATE TRIGGER update_user_profiles_modtime
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_modified_column();

-- ============================================================================
-- 5. Telegram Bot RPCs (Bypass RLS)
-- These functions run with SECURITY DEFINER to allow the backend bot to 
-- securely read phone numbers and link chat IDs without exposing the table.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.bot_get_profiles()
RETURNS TABLE(id UUID, phone_number TEXT, full_name TEXT, birth_date DATE, telegram_chat_id TEXT) AS $$
BEGIN
    RETURN QUERY SELECT p.id, p.phone_number, p.full_name, p.birth_date, p.telegram_chat_id FROM public.user_profiles p;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION public.bot_link_telegram(p_user_id UUID, p_chat_id TEXT)
RETURNS void AS $$
BEGIN
    UPDATE public.user_profiles
    SET telegram_chat_id = p_chat_id
    WHERE id = p_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION public.bot_get_bookings(p_user_id UUID, p_booking_type TEXT)
RETURNS TABLE(provider_name TEXT, pnr_or_confirmation_number TEXT, travel_date DATE, details JSONB) AS $$
BEGIN
    RETURN QUERY 
    SELECT b.provider_name, b.pnr_or_confirmation_number, b.travel_date, b.details
    FROM public.bookings b
    WHERE b.user_id = p_user_id AND b.booking_type = p_booking_type
    ORDER BY b.booking_date DESC
    LIMIT 5;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- 6. Emergency Contact Columns (SOS Feature)
-- Run this AFTER the initial migration if the table already exists.
-- ============================================================================

ALTER TABLE public.user_profiles
    ADD COLUMN IF NOT EXISTS emergency_contact_name TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS emergency_contact_phone TEXT DEFAULT '';

-- RPC to fetch emergency contact (bypasses RLS for the bot)
CREATE OR REPLACE FUNCTION public.bot_get_emergency_contact(p_user_id UUID)
RETURNS TABLE(full_name TEXT, emergency_contact_name TEXT, emergency_contact_phone TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT p.full_name, p.emergency_contact_name, p.emergency_contact_phone
    FROM public.user_profiles p
    WHERE p.id = p_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- ============================================================================
-- 7. Chat Sessions (Persistent Chat History Sidebar)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    thread_id   TEXT NOT NULL UNIQUE,
    title       TEXT DEFAULT 'New Conversation',
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON public.chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON public.chat_sessions(updated_at DESC);

-- Enable RLS for chat sessions
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own chat sessions"
    ON public.chat_sessions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own chat sessions"
    ON public.chat_sessions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own chat sessions"
    ON public.chat_sessions FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own chat sessions"
    ON public.chat_sessions FOR DELETE
    USING (auth.uid() = user_id);

-- Auto-update updated_at on chat session changes
DROP TRIGGER IF EXISTS update_chat_sessions_modtime ON public.chat_sessions;
CREATE TRIGGER update_chat_sessions_modtime
    BEFORE UPDATE ON public.chat_sessions
    FOR EACH ROW EXECUTE FUNCTION public.update_modified_column();
