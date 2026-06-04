import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Linkedin, Lock, Loader, Mail } from 'lucide-react';
import toast from 'react-hot-toast';
import apiService from '../services/apiService';
import { useAuthStore } from '../store/authStore';

const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { setUser, setToken, logout } = useAuthStore();

  const handleOAuthLogin = (provider: 'google' | 'linkedin') => {
    window.location.href = apiService.getOAuthStartUrl(provider);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email || !password) {
      toast.error('Please fill in all fields');
      return;
    }

    try {
      setLoading(true);
      const response = await apiService.login(email, password);

      // Store token and user info
      setToken(response.access_token);
      setUser({
        id: response.user_id,
        email: response.email,
        full_name: response.email.split('@')[0], // Placeholder
        role: response.role,
      });

      toast.success('Login successful!');
      navigate('/');
    } catch (error: any) {
      logout();
      toast.error(error.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 to-blue-800 flex items-center justify-center px-4">
      <div className="bg-white rounded-lg shadow-xl p-8 w-full max-w-md">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">TenderEval</h1>
        <p className="text-gray-600 mb-6">AI-Powered Tender Evaluation Platform</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Email */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <div className="relative">
              <Mail className="absolute left-3 top-3 text-gray-400" size={20} />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                placeholder="your@email.com"
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-3 text-gray-400" size={20} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                placeholder="••••••••"
              />
            </div>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center justify-center space-x-2"
          >
            {loading && <Loader size={20} className="animate-spin" />}
            <span>{loading ? 'Logging in...' : 'Login'}</span>
          </button>
        </form>

        <div className="mt-5">
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <div className="h-px flex-1 bg-gray-200" />
            <span>or</span>
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3">
            <button
              type="button"
              onClick={() => handleOAuthLogin('google')}
              className="w-full border border-gray-300 text-gray-800 py-2 rounded-lg font-medium hover:bg-gray-50 transition flex items-center justify-center gap-2"
            >
              <span className="text-lg font-semibold text-blue-600">G</span>
              <span>Continue with Google</span>
            </button>
            <button
              type="button"
              onClick={() => handleOAuthLogin('linkedin')}
              className="w-full border border-gray-300 text-gray-800 py-2 rounded-lg font-medium hover:bg-gray-50 transition flex items-center justify-center gap-2"
            >
              <Linkedin size={20} className="text-blue-700" />
              <span>Continue with LinkedIn</span>
            </button>
          </div>
        </div>

        {/* Signup Link */}
        <p className="text-center text-gray-600 mt-6">
          Don't have an account?{' '}
          <Link to="/signup" className="text-blue-600 font-medium hover:underline">
            Sign up
          </Link>
        </p>

        {/* Demo Credentials */}
        <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
          
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
