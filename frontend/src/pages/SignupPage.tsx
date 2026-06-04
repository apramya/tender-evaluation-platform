import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Building, Linkedin, Loader, Lock, Mail, User } from 'lucide-react';
import toast from 'react-hot-toast';
import apiService from '../services/apiService';
import { useAuthStore } from '../store/authStore';

const SignupPage: React.FC = () => {
  const publicSignupEnabled = process.env.REACT_APP_ALLOW_PUBLIC_SIGNUP !== 'false';
  const [formData, setFormData] = useState({
    full_name: '',
    email: '',
    password: '',
    confirmPassword: '',
    organization: '',
  });
  const [otp, setOtp] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { setUser, setToken, logout } = useAuthStore();

  const handleOAuthSignup = (provider: 'google' | 'linkedin') => {
    window.location.href = apiService.getOAuthStartUrl(provider);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (!formData.full_name || !formData.email || !formData.password || !formData.confirmPassword) {
      toast.error('Please fill in all fields');
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }

    if (formData.password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    try {
      setLoading(true);
      await apiService.requestSignupOtp(
        formData.email,
        formData.password,
        formData.full_name,
        formData.organization
      );
      setOtpSent(true);
      toast.success('Verification code sent to your email');
    } catch (error: any) {
      logout();
      toast.error(error.response?.data?.detail || 'Could not send verification code');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otp.trim()) {
      toast.error('Enter the verification code');
      return;
    }

    try {
      setLoading(true);
      const response = await apiService.verifySignupOtp(formData.email, otp.trim());

      setToken(response.access_token);
      setUser({
        id: response.user_id,
        email: response.email,
        full_name: formData.full_name,
        role: response.role,
        organization: formData.organization,
      });

      toast.success('Account created successfully!');
      navigate('/');
    } catch (error: any) {
      logout();
      toast.error(error.response?.data?.detail || 'Verification failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 to-blue-800 flex items-center justify-center px-4">
      <div className="bg-white rounded-lg shadow-xl p-8 w-full max-w-md">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Create Account</h1>
        <p className="text-gray-600 mb-6">
          {publicSignupEnabled
            ? 'Join the Tender Evaluation Platform'
            : 'Accounts are created by the administrator.'}
        </p>

        {!publicSignupEnabled ? (
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
            Use the login page if your administrator has already created your account.
          </div>
        ) : otpSent ? (
        <form onSubmit={handleVerifyOtp} className="space-y-4">
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
            Enter the verification code sent to {formData.email}.
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Verification code</label>
            <input
              type="text"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
              placeholder="6-digit code"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center justify-center space-x-2"
          >
            {loading && <Loader size={20} className="animate-spin" />}
            <span>{loading ? 'Verifying...' : 'Verify and Create Account'}</span>
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => setOtpSent(false)}
            className="w-full border border-gray-300 text-gray-700 py-2 rounded-lg font-medium hover:bg-gray-50 transition"
          >
            Edit details
          </button>
        </form>
        ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Full Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
            <div className="relative">
              <User className="absolute left-3 top-3 text-gray-400" size={20} />
              <input
                type="text"
                name="full_name"
                value={formData.full_name}
                onChange={handleChange}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                placeholder="John Doe"
              />
            </div>
          </div>

          {/* Organization */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Organization</label>
            <div className="relative">
              <Building className="absolute left-3 top-3 text-gray-400" size={20} />
              <input
                type="text"
                name="organization"
                value={formData.organization}
                onChange={handleChange}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                placeholder="Your Company"
              />
            </div>
          </div>

          {/* Email */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <div className="relative">
              <Mail className="absolute left-3 top-3 text-gray-400" size={20} />
              <input
                type="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
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
                name="password"
                value={formData.password}
                onChange={handleChange}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                placeholder="••••••••"
              />
            </div>
          </div>

          {/* Confirm Password */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Confirm Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-3 text-gray-400" size={20} />
              <input
                type="password"
                name="confirmPassword"
                value={formData.confirmPassword}
                onChange={handleChange}
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
            <span>{loading ? 'Creating Account...' : 'Create Account'}</span>
          </button>
        </form>
        )}

        <div className="mt-5">
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <div className="h-px flex-1 bg-gray-200" />
            <span>or</span>
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3">
            <button
              type="button"
              onClick={() => handleOAuthSignup('google')}
              className="w-full border border-gray-300 text-gray-800 py-2 rounded-lg font-medium hover:bg-gray-50 transition flex items-center justify-center gap-2"
            >
              <span className="text-lg font-semibold text-blue-600">G</span>
              <span>Continue with Google</span>
            </button>
            <button
              type="button"
              onClick={() => handleOAuthSignup('linkedin')}
              className="w-full border border-gray-300 text-gray-800 py-2 rounded-lg font-medium hover:bg-gray-50 transition flex items-center justify-center gap-2"
            >
              <Linkedin size={20} className="text-blue-700" />
              <span>Continue with LinkedIn</span>
            </button>
          </div>
        </div>

        {/* Login Link */}
        <p className="text-center text-gray-600 mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-blue-600 font-medium hover:underline">
            Login
          </Link>
        </p>
      </div>
    </div>
  );
};

export default SignupPage;
