import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { fetchLocalityRentalData } from './services/localities';
import {
  getHyderabadRentSummary,
  getOneBedroomRentEstimate,
} from './services/hyderabadRentData';
import { getHyderabadRentalInsight } from './services/hyderabadRentalInsights';
import { readApiResponse } from './services/apiResponse';
import CitySearch from './components/map/CitySearch';
import RentTraceChat from './components/chat/RentTraceChat';

const RentTraceMap = lazy(() => import('./components/map/RentTraceMap'));

const DEFAULT_MAP_CITY = {
  name: 'Hyderabad',
  displayName: 'Hyderabad, Telangana, India',
  center: [17.385, 78.4867],
  bounds: null,
  zoom: 11,
};

function formatRent(value) {
  return `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}

function App() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [formData, setFormData] = useState({ name: '', email: '', password: '' });
  const [rememberMe, setRememberMe] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [userName, setUserName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [userRole, setUserRole] = useState('user');
  const [mapCity, setMapCity] = useState(DEFAULT_MAP_CITY);
  const [selectedLocality, setSelectedLocality] = useState(null);
  const [localityAnalysis, setLocalityAnalysis] = useState(null);
  const [localityAnalysisLoading, setLocalityAnalysisLoading] = useState(false);
  const [localityAnalysisError, setLocalityAnalysisError] = useState('');
  const [showRentInsight, setShowRentInsight] = useState(false);
  const [pendingLandAction, setPendingLandAction] = useState(null);
  const [chatSelectedContext, setChatSelectedContext] = useState(null);
  const localityRequestRef = useRef(null);
  const handleChatContextChange = useCallback((context) => {
    setChatSelectedContext(context);
  }, []);
  const rentInsight = selectedLocality && localityAnalysis
    ? getHyderabadRentalInsight(selectedLocality.name, {
        ...(localityAnalysis.summary ?? {}),
        trend: localityAnalysis.datasetBacked
          ? localityAnalysis.summary.trend
          : localityAnalysis.trend,
      })
    : null;
  const oneBedroomRentEstimate = localityAnalysis?.datasetBacked
    && localityAnalysis.summary?.oneBedroomRent == null
    && selectedLocality
    ? getOneBedroomRentEstimate(selectedLocality.name)
    : null;

  useEffect(() => {
    if (!pendingLandAction || localityAnalysisLoading) {
      return;
    }
    if (
      selectedLocality?.name?.toLocaleLowerCase()
      !== pendingLandAction.localityName.toLocaleLowerCase()
    ) {
      return;
    }
    if (!localityAnalysis) {
      setPendingLandAction(null);
      return;
    }

    if (pendingLandAction.action === 'rent-history') {
      document.getElementById('locality-rental-analysis')?.scrollIntoView({ behavior: 'smooth' });
    } else if (pendingLandAction.action === 'rent-insight' && rentInsight) {
      setShowRentInsight(true);
    }
    setPendingLandAction(null);
  }, [
    pendingLandAction,
    localityAnalysisLoading,
    selectedLocality,
    localityAnalysis,
    rentInsight,
  ]);

  useEffect(() => {
    const oauthError = new URLSearchParams(window.location.search).get('oauth_error');
    if (oauthError) {
      const messages = {
        not_configured: 'Google sign-in is not configured in the active backend. Check /api/auth/oauth/google/config-status and restart FastAPI after updating the project-root .env file.',
        cancelled: 'Sign-in was cancelled.',
        invalid_state: 'Sign-in could not be verified. Please try again.',
        failed: 'Google sign-in failed. Please try again.',
      };
      setError(messages[oauthError] || 'Sign-in failed. Please try again.');
    }

    const initializeApp = async () => {
      try {
        const response = await fetch('/api/overview');
        if (!response.ok) {
          throw new Error('Failed to fetch overview');
        }
        const data = await response.json();
        setOverview(data);
      } catch (error) {
        setOverview({
          city: 'Hyderabad',
          average_rent: 27000,
          monthly_change: 1.9,
          market_status: 'Stable',
          localities: ['Gachibowli', 'Madhapur'],
          data_notice: 'DEMO DATA: These Hyderabad chart values are synthetic examples, not real-world market observations.',
          trend: [
            { month: 'May 26', price: 25250 },
            { month: 'Jun 26', price: 25750 },
            { month: 'Jul 26', price: 26250 },
            { month: 'Aug 26', price: 26750 },
            { month: 'Sep 26', price: 27250 },
            { month: 'Oct 26', price: 27750 },
          ],
        });
      } finally {
        try {
          const sessionResponse = await fetch('/api/session');
          if (sessionResponse.ok) {
            const { authenticated, user } = await sessionResponse.json();
            if (authenticated && user) {
              setUserName(user.name);
              setUserEmail(user.email);
              setUserRole(user.role || 'user');
              setIsAuthenticated(true);
              await loadDashboard(user.email, user.role || 'user');
            } else {
              setIsAuthenticated(false);
            }
          }
        } catch {
          setIsAuthenticated(false);
        }
        setLoading(false);
      }
    };

    initializeApp();
  }, []);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const loadDashboard = async (email, role) => {
    try {
      let response;
      if (role === 'admin') {
        response = await fetch('/api/admin/overview');
      } else {
        response = await fetch('/api/overview');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to load dashboard data');
      }

      const data = await response.json();
      setOverview(data.summary ? { ...data.summary, city: 'Admin overview' } : data);
    } catch (loadError) {
      setError(loadError.message || 'Unable to load dashboard data.');
    }
  };

  const handleSelectLocality = async (locality) => {
    localityRequestRef.current?.abort();
    localityRequestRef.current = null;
    setSelectedLocality(locality);
    setLocalityAnalysis(null);
    setLocalityAnalysisError('');
    setShowRentInsight(false);
    if (!locality) {
      setLocalityAnalysisLoading(false);
      return;
    }

    const datasetSummary = getHyderabadRentSummary(locality.name);
    if (datasetSummary) {
      setSelectedLocality({ ...locality, datasetBacked: true });
      setLocalityAnalysis({
        datasetBacked: true,
        summary: datasetSummary,
        analysis: {
          average_rent: datasetSummary.averageRent,
          latest_market_observation: '2026 (workbook)',
        },
        trend: datasetSummary.trend.map((observation) => ({
          observation_date: `${observation.year}-01-01`,
          average_rent: observation.averageRent,
        })),
        rentals: [],
      });
      setLocalityAnalysisLoading(false);
      return;
    }

    const controller = new AbortController();
    localityRequestRef.current = controller;
    setLocalityAnalysisLoading(true);

    try {
      setLocalityAnalysis(await fetchLocalityRentalData(locality.id, controller.signal));
    } catch (analysisError) {
      if (!controller.signal.aborted) {
        setLocalityAnalysisError(analysisError.message || 'Unable to load locality rental data.');
      }
    } finally {
      if (!controller.signal.aborted) {
        setLocalityAnalysisLoading(false);
        localityRequestRef.current = null;
      }
    }
  };

  const handleLandAnalysisAction = (action, locality) => {
    setPendingLandAction({ action, localityName: locality.name });
    void handleSelectLocality(locality);
  };

  const handleCitySelect = (city) => {
    localityRequestRef.current?.abort();
    localityRequestRef.current = null;
    setMapCity({
      name: city.name,
      displayName: city.display_name,
      center: city.center,
      bounds: city.bounds,
    });
    setSelectedLocality(null);
    setChatSelectedContext(null);
    setLocalityAnalysis(null);
    setLocalityAnalysisError('');
    setLocalityAnalysisLoading(false);
  };

  const completeLogin = async (email, password) => {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password, remember_me: rememberMe }),
    });

    const data = await readApiResponse(response, 'Login');
    if (!data.user || typeof data.user.name !== 'string' || typeof data.user.email !== 'string') {
      throw new Error('Login returned an invalid response: the expected user details are missing.');
    }

    setError('');
    setUserName(data.user.name);
    setUserEmail(data.user.email);
    setUserRole(data.user.role || 'user');
    setIsAuthenticated(true);
    await loadDashboard(data.user.email, data.user.role || 'user');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    const email = formData.email.trim();
    const password = formData.password.trim();

    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }

    if (!email.includes('@')) {
      setError('Please enter a valid email address.');
      return;
    }

    try {
      await completeLogin(email, password);
    } catch (loginError) {
      setError(loginError.message || 'Login failed. Please try again.');
    }
  };

  const handleSignup = async (event) => {
    event.preventDefault();

    const name = formData.name.trim();
    const email = formData.email.trim();
    const password = formData.password.trim();

    if (!name || !email || !password) {
      setError('Please fill in your name, email, and password.');
      return;
    }

    try {
      const response = await fetch('/api/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name,
          email,
          password,
        }),
      });

      const data = await readApiResponse(response, 'Signup');
      if (!data.user || typeof data.user.email !== 'string') {
        throw new Error('Signup returned an invalid response: the expected user details are missing.');
      }

      setError('');
      setAuthMode('login');
      setFormData({ name: '', email: '', password: '' });
      setError('Account created successfully. You can now sign in.');
    } catch (signupError) {
      setError(signupError.message || 'Signup failed. Please try again.');
    }
  };

  const handleDemoLogin = async () => {
    const demoEmail = 'demo@renttrace.com';
    const demoPassword = 'demo123';
    setFormData({ name: '', email: demoEmail, password: demoPassword });

    try {
      await completeLogin(demoEmail, demoPassword);
    } catch (loginError) {
      setError(loginError.message || 'Demo login failed.');
    }
  };

  const handleOAuthLogin = (provider) => {
    window.location.assign(`/api/auth/oauth/${provider}?remember_me=${rememberMe}`);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 text-slate-700">
        Loading RentTrace...
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 px-4 py-10 text-white">
        <div className="mx-auto grid max-w-6xl gap-8 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="flex flex-col justify-center rounded-[28px] border border-white/10 bg-white/5 p-8 backdrop-blur-sm">
            <div className="mb-8 flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-500 font-bold text-white">
                R
              </div>
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-blue-200">RentTrace</p>
              </div>
            </div>

            <div className="max-w-xl">
              <h1 className="text-4xl font-bold leading-tight sm:text-5xl">
                Understand rent trends before the market moves.
              </h1>
              <p className="mt-5 text-lg text-slate-300">
                Track neighborhood pricing, compare localities, and spot emerging rental patterns across the city.
              </p>
            </div>

            <div className="mt-10 grid gap-4 sm:grid-cols-3">
              <FeatureStat value="18K+" label="Property snapshots" />
              <FeatureStat value="42" label="Locality signals" />
              <FeatureStat value="12" label="Trend windows" />
            </div>
          </div>

          <div className="rounded-[28px] bg-white p-8 text-slate-900 shadow-2xl ring-1 ring-slate-200">
            <div className="mb-6 text-center">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-600">
                {authMode === 'login' ? 'Welcome back' : 'Create account'}
              </p>
              <h2 className="mt-3 text-3xl font-bold">{authMode === 'login' ? 'Sign in' : 'Sign up'}</h2>
            </div>

            <div className="mb-5 grid grid-cols-1 gap-3">
              <button type="button" onClick={() => handleOAuthLogin('google')} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-100">
                Google
              </button>
            </div>

            <div className="mb-5 flex items-center gap-3 text-xs uppercase tracking-[0.2em] text-slate-400">
              <div className="h-px flex-1 bg-slate-200" />
              <span>{authMode === 'login' ? 'or continue with email' : 'sign up with email'}</span>
              <div className="h-px flex-1 bg-slate-200" />
            </div>

            {authMode === 'login' ? (
              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <label htmlFor="email" className="mb-2 block text-sm font-medium text-slate-700">
                    Email address
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    value={formData.email}
                    onChange={handleChange}
                    placeholder="you@example.com"
                    className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                <div>
                  <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      id="password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      value={formData.password}
                      onChange={handleChange}
                      placeholder="Enter your password"
                      className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-3 pr-11 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((current) => !current)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-sm font-medium text-slate-500 hover:text-slate-700"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? 'Hide' : 'Show'}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between gap-3 text-sm">
                  <label className="flex items-center gap-2 text-slate-600">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(event) => setRememberMe(event.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    Remember me
                  </label>
                  <button type="button" className="font-medium text-blue-600 hover:text-blue-500">
                    Forgot password?
                  </button>
                </div>

                {error && <p className="text-sm text-red-600">{error}</p>}

                <button
                  type="submit"
                  className="w-full rounded-xl bg-blue-600 px-4 py-3 font-semibold text-white transition hover:bg-blue-500"
                >
                  Login
                </button>

                <button
                  type="button"
                  onClick={handleDemoLogin}
                  className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-semibold text-slate-700 transition hover:bg-slate-50"
                >
                  Use demo account
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setError('');
                    setAuthMode('signup');
                    setFormData({ name: '', email: '', password: '' });
                  }}
                  className="w-full text-center text-sm font-medium text-blue-600 hover:text-blue-500"
                >
                  Create a new account
                </button>
              </form>
            ) : (
              <form onSubmit={handleSignup} className="space-y-5">
                <div>
                  <label htmlFor="name" className="mb-2 block text-sm font-medium text-slate-700">
                    Full name
                  </label>
                  <input
                    id="name"
                    name="name"
                    type="text"
                    value={formData.name}
                    onChange={handleChange}
                    placeholder="Jane Doe"
                    className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                <div>
                  <label htmlFor="signup-email" className="mb-2 block text-sm font-medium text-slate-700">
                    Email address
                  </label>
                  <input
                    id="signup-email"
                    name="email"
                    type="email"
                    value={formData.email}
                    onChange={handleChange}
                    placeholder="you@example.com"
                    className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                <div>
                  <label htmlFor="signup-password" className="mb-2 block text-sm font-medium text-slate-700">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      id="signup-password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      value={formData.password}
                      onChange={handleChange}
                      placeholder="Create a secure password"
                      className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-3 pr-11 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((current) => !current)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-sm font-medium text-slate-500 hover:text-slate-700"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? 'Hide' : 'Show'}
                    </button>
                  </div>
                </div>

                {error && <p className="text-sm text-red-600">{error}</p>}

                <button
                  type="submit"
                  className="w-full rounded-xl bg-blue-600 px-4 py-3 font-semibold text-white transition hover:bg-blue-500"
                >
                  Create account
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setError('');
                    setAuthMode('login');
                    setFormData({ name: '', email: '', password: '' });
                  }}
                  className="w-full text-center text-sm font-medium text-blue-600 hover:text-blue-500"
                >
                  Back to login
                </button>
              </form>
            )}

            <p className="mt-6 text-center text-xs text-slate-500">
              Secure account access for RentTrace.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800">
      <header className="bg-slate-900 text-white shadow-md">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-3 py-4 sm:flex-nowrap sm:px-6 sm:py-6">
          <div>
            <h1 className="text-3xl font-bold">RentTrace</h1>
            <p className="mt-2 text-slate-300">{userRole === 'admin' ? 'Administration dashboard' : 'Urban rental analytics overview'}</p>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium text-slate-300">Welcome, {userName}</span>
            <button
              type="button"
              onClick={() => {
                fetch('/api/logout', { method: 'POST' }).finally(() => {
                  setIsAuthenticated(false);
                  setUserName('');
                  setUserEmail('');
                  setUserRole('user');
                  setFormData({ name: '', email: '', password: '' });
                  setError('');
                });
              }}
              className="rounded-lg border border-slate-600 px-3 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-3 py-5 sm:px-6 sm:py-8">
        <CitySearch onCitySelect={handleCitySelect} />
        <Suspense fallback={<div className="mb-8 h-24 animate-pulse rounded-2xl bg-white ring-1 ring-slate-200" />}>
          <RentTraceMap
            center={mapCity.center}
            zoom={mapCity.zoom}
            bounds={mapCity.bounds}
            cityName={mapCity.name}
            selectedLocality={selectedLocality}
            onLocalitySelect={handleSelectLocality}
            onViewLocalityAnalysis={handleSelectLocality}
            onLandAnalysisAction={handleLandAnalysisAction}
            onChatContextChange={handleChatContextChange}
          />
        </Suspense>
        {overview.data_notice && (
          <p className="mb-5 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-900">
            {overview.data_notice}
          </p>
        )}
        {userRole === 'admin' && overview && overview.summary ? (
          <section className="space-y-6">
            <div className="grid gap-4 md:grid-cols-4">
              <StatCard label="Total Users" value={overview.summary.total_users} />
              <StatCard label="Active Listings" value={overview.summary.active_listings} />
              <StatCard label="Localities" value={overview.summary.localities} />
              <StatCard label="Account" value="Administrator" />
            </div>

            <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
              <h2 className="mb-2 text-xl font-semibold">Admin overview</h2>
              <p className="text-sm text-slate-500">
                Access granted to {userEmail}. Generated at {overview.summary.generated_at}
              </p>
            </div>
          </section>
        ) : (
          <>
            <section className="grid gap-4 md:grid-cols-4">
              <StatCard label="City" value={overview.city} />
              <StatCard label="Avg. Rent" value={`₹${overview.average_rent.toLocaleString()}`} />
              <StatCard label="Monthly Change" value={`${overview.monthly_change}%`} />
              <StatCard label="Market" value={overview.market_status} />
            </section>

            <section className="mt-8 grid gap-6 lg:grid-cols-[2fr_1fr]">
              <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
                <h2 className="mb-4 text-xl font-semibold">{overview.city} rental trend</h2>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={overview.trend || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="month" stroke="#64748b" />
                      <YAxis stroke="#64748b" />
                      <Tooltip />
                      <Line type="monotone" dataKey="price" stroke="#2563eb" strokeWidth={3} dot={{ r: 4 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
                <h2 className="mb-4 text-xl font-semibold">Top localities</h2>
                <ul className="space-y-3">
                  {(overview.localities || []).map((locality, index) => (
                    <li key={locality} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                      <span>{index + 1}. {locality}</span>
                      <span className="text-sm text-slate-500">Active</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          </>
        )}
        {selectedLocality && (
          <section id="locality-rental-analysis" className="mt-8 space-y-6" aria-live="polite">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-700">Locality rental data</p>
                  <div className="mt-1 flex flex-wrap items-center gap-3">
                    <h2 className="text-xl font-semibold text-slate-900">{selectedLocality.name}</h2>
                    {!localityAnalysis?.datasetBacked && selectedLocality.description?.match(/demo|synthetic/i) && (
                      <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900">
                        DEMO DATA
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-slate-600">
                    {selectedLocality.city || 'Hyderabad'}, {selectedLocality.state || 'Telangana'}
                    {selectedLocality.latitude != null && selectedLocality.longitude != null
                      ? ` · ${Number(selectedLocality.latitude).toFixed(5)}, ${Number(selectedLocality.longitude).toFixed(5)}`
                      : ' · Looking up map coordinates'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleSelectLocality(null)}
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  Close
                </button>
              </div>
              {!localityAnalysis?.datasetBacked && selectedLocality.description?.match(/demo|synthetic/i) && (
                <p className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  These clearly labelled RentTrace sample observations are synthetic demonstrations, not real-world rental quotes.
                </p>
              )}
              <div className="mt-4 border-t border-slate-100 pt-4 text-sm text-slate-600">
                {localityAnalysisLoading && <p role="status">Loading locality rental data...</p>}
                {localityAnalysisError && <p role="alert" className="text-rose-700">{localityAnalysisError}</p>}
                {localityAnalysis?.datasetBacked && (
                  <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <RentSummaryCard
                      label="1 BHK"
                      value={localityAnalysis.summary.oneBedroomRent == null
                        ? oneBedroomRentEstimate
                          ? `≈ ${formatRent(oneBedroomRentEstimate.rent)}`
                          : 'Not listed'
                        : formatRent(localityAnalysis.summary.oneBedroomRent)}
                      detail={oneBedroomRentEstimate
                        ? `Estimated from 1-to-2 BHK rent ratios across ${oneBedroomRentEstimate.peerLocalityCount} localities (${oneBedroomRentEstimate.year} dataset); not a direct listing.`
                        : null}
                    />
                    <RentSummaryCard
                      label="2 BHK"
                      value={localityAnalysis.summary.twoBedroomRent == null
                        ? 'Not listed'
                        : formatRent(localityAnalysis.summary.twoBedroomRent)}
                    />
                    <RentSummaryCard
                      label="Average rent · 2026"
                      value={localityAnalysis.summary.averageRent == null
                        ? 'Not available'
                        : formatRent(localityAnalysis.summary.averageRent)}
                    />
                    <RentSummaryCard
                      label="Trend · 2017–2026"
                      value={localityAnalysis.summary.trendPercent == null
                        ? 'Not available'
                        : `${localityAnalysis.summary.trendPercent >= 0 ? '↑' : '↓'} ${Math.abs(localityAnalysis.summary.trendPercent).toFixed(1)}%`}
                      positive={localityAnalysis.summary.trendPercent == null
                        || localityAnalysis.summary.trendPercent >= 0}
                    />
                  </div>
                )}
                {localityAnalysis && (
                  <div className="mb-5">
                    <button
                      type="button"
                      aria-expanded={showRentInsight}
                      aria-controls="rent-change-insight"
                      aria-haspopup="dialog"
                      onClick={() => setShowRentInsight(true)}
                      className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-800 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2"
                    >
                      <span aria-hidden="true">🤖</span>
                      Why did rent change?
                    </button>
                  </div>
                )}
                {localityAnalysis && !localityAnalysis.datasetBacked && (
                  <div className="mb-5 flex flex-wrap gap-x-8 gap-y-2">
                    <p>
                      Latest recorded rent:{' '}
                      <span className="font-semibold text-slate-900">
                        {localityAnalysis.analysis.average_rent == null
                          ? 'No rent recorded'
                          : formatRent(localityAnalysis.analysis.average_rent)}
                      </span>
                    </p>
                    <p>
                      Latest observation:{' '}
                      <span className="font-semibold text-slate-900">
                        {localityAnalysis.analysis.latest_market_observation || 'Not available'}
                      </span>
                    </p>
                  </div>
                )}
                {localityAnalysis && !localityAnalysis.datasetBacked && (
                  localityAnalysis.rentals.length > 0 ? (
                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                      <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                          <tr>
                            <th scope="col" className="px-4 py-3">Observation date</th>
                            <th scope="col" className="px-4 py-3">Rent</th>
                            <th scope="col" className="px-4 py-3">Security deposit</th>
                            <th scope="col" className="px-4 py-3">Rent / sq ft</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {localityAnalysis.rentals.map((rental) => (
                            <tr key={rental.id}>
                              <td className="whitespace-nowrap px-4 py-3">{rental.observation_date}</td>
                              <td className="whitespace-nowrap px-4 py-3 font-medium text-slate-900">{formatRent(rental.rent)}</td>
                              <td className="whitespace-nowrap px-4 py-3">
                                {rental.security_deposit == null ? '—' : formatRent(rental.security_deposit)}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3">
                                {rental.price_per_sqft == null ? '—' : `₹${Number(rental.price_per_sqft).toLocaleString('en-IN')}`}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p>No rental observations are recorded for this locality yet.</p>
                  )
                )}
              </div>
            </div>

            <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
              <div className="mb-4">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-700">
                  {localityAnalysis?.datasetBacked
                    ? 'Rental history'
                    : selectedLocality.description?.match(/demo|synthetic/i)
                      ? 'RentTrace demo graph'
                      : 'Rent trend'}
                </p>
                <h2 className="mt-1 text-xl font-semibold text-slate-900">{selectedLocality.name} rent trend</h2>
              </div>
              {localityAnalysisLoading ? (
                <p role="status" className="py-12 text-center text-sm text-slate-500">Loading rent trend...</p>
              ) : localityAnalysis?.trend.length ? (
                <div className="h-80" aria-label={`${selectedLocality.name} rent trend chart`}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={localityAnalysis.trend.map((observation) => ({
                        month: observation.observation_date?.slice(0, 7) || 'Unknown date',
                        rent: Number(observation.average_rent),
                      }))}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="month" stroke="#64748b" />
                      <YAxis stroke="#64748b" tickFormatter={formatRent} />
                      <Tooltip formatter={(value) => [formatRent(value), 'Average rent']} />
                      <Line type="monotone" dataKey="rent" name="Average rent" stroke="#047857" strokeWidth={3} dot={{ r: 4 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="py-12 text-center text-sm text-slate-500">
                  {localityAnalysisError || 'No rent trend observations are available for this locality yet.'}
                </p>
              )}
            </div>
          </section>
        )}
        {showRentInsight && selectedLocality && rentInsight && (
          <RentChangeInsight
            id="rent-change-insight"
            localityName={selectedLocality.name}
            insight={rentInsight}
            onClose={() => setShowRentInsight(false)}
          />
        )}
      </main>
      <RentTraceChat selectedContext={chatSelectedContext} />
    </div>
  );
}

function FeatureStat({ value, label }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/30 p-4 backdrop-blur-sm">
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="mt-2 text-sm text-slate-300">{label}</p>
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

function RentSummaryCard({ label, value, positive = true, detail = null }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${positive ? 'text-slate-900' : 'text-rose-700'}`}>
        {value}
      </p>
      {detail && <p className="mt-1 text-xs leading-relaxed text-amber-800">{detail}</p>}
    </div>
  );
}

function RentChangeInsight({ id, localityName, insight, onClose }) {
  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const isIncrease = insight.trendPercent != null && insight.trendPercent >= 0;
  const changeText = insight.trendPercent == null
    ? 'There is not enough dated rent history to calculate a percentage change.'
    : `Rent ${isIncrease ? 'increased' : 'decreased'} by approximately ${Math.abs(insight.trendPercent).toFixed(1)}% between ${insight.period}.`;

  return (
    <div
      className="fixed inset-0 z-[3000] flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-sm sm:p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        id={id}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl sm:p-7"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 id={`${id}-title`} className="text-lg font-bold uppercase tracking-wide text-slate-900 sm:text-xl">
                Why did rent change?
              </h3>
              <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900">
                Estimated Insight
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-500">{localityName}, Hyderabad</p>
          </div>
          <button
            type="button"
            autoFocus
            onClick={onClose}
            className="shrink-0 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-emerald-600"
          >
            Close
          </button>
        </div>

        <div className="mt-5 rounded-xl bg-emerald-50 p-4">
          <p className="text-sm font-semibold text-slate-900">{changeText}</p>
          {insight.rentStart != null && insight.rentEnd != null && (
            <p className="mt-1 text-sm text-slate-700">
              {insight.period}: {formatRent(insight.rentStart)} → {formatRent(insight.rentEnd)} · {insight.rentConfidence}
            </p>
          )}
          <p className="mt-2 text-xs leading-relaxed text-slate-600">
            {insight.areaSpecific
              ? 'This is the supplied 2-BHK annual series; it is a different measure and period from the locality-average trend card.'
              : 'This uses the available RentTrace locality-average history because the supplied 2-BHK insight file has no matching area series.'}
          </p>
        </div>

        <div className="mt-5">
          <h4 className="text-sm font-semibold text-slate-900">Potential factors</h4>
          <p className="mt-1 text-xs text-slate-500">
            Supplied indicators and their scope—not measured causal impacts.
          </p>
          <div className="mt-3 overflow-hidden rounded-xl border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
                <tr>
                  <th scope="col" className="px-3 py-3 sm:px-4">Factor</th>
                  <th scope="col" className="px-3 py-3 sm:px-4">Evidence in supplied data</th>
                  <th scope="col" className="px-3 py-3 sm:px-4">Coverage</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {insight.factors.map((item) => (
                  <tr key={item.label} className="align-top">
                    <th scope="row" className="min-w-36 px-3 py-3 font-medium text-slate-800 sm:px-4">{item.label}</th>
                    <td className="px-3 py-3 leading-relaxed text-slate-700 sm:px-4">{item.evidence}</td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs font-medium text-slate-600 sm:px-4">{item.coverage}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50/70 p-4">
          <h4 className="text-sm font-semibold text-emerald-950">RentTrace Insight</h4>
          <p className="mt-1 text-sm leading-relaxed text-slate-700">{insight.explanation}</p>
        </div>

        <details className="mt-4 rounded-lg border border-slate-200 px-4 py-3">
          <summary className="cursor-pointer text-sm font-semibold text-slate-800">Data sources and methods</summary>
          <ul className="mt-3 space-y-3">
            {insight.methodNotes.map((note) => (
              <li key={note.column} className="text-xs leading-relaxed text-slate-600">
                <span className="font-semibold text-slate-800">{note.column} · {note.type}:</span>{' '}
                {note.source_or_method}
              </li>
            ))}
          </ul>
        </details>

        <p className="mt-4 text-xs leading-relaxed text-slate-500">
          This is an estimated, descriptive insight based on the supplied CSVs. Rent overlap with these indicators
          does not prove causation. No trained causal model or saved model feature-importance results are available
          in this project database.
        </p>
      </section>
    </div>
  );
}

export default App;
