import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuthStore } from '../store/authStore';

const OAuthCallbackPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setUser, setToken } = useAuthStore();

  useEffect(() => {
    const token = searchParams.get('token');
    const userId = searchParams.get('user_id');
    const email = searchParams.get('email');
    const role = searchParams.get('role');
    const fullName = searchParams.get('full_name');
    const error = searchParams.get('oauth_error');

    if (error || !token || !userId || !email || !role) {
      toast.error(error || 'OAuth login failed');
      navigate('/login', { replace: true });
      return;
    }

    setToken(token);
    setUser({
      id: userId,
      email,
      full_name: fullName || email.split('@')[0],
      role,
    });

    toast.success('Login successful!');
    navigate('/', { replace: true });
  }, [navigate, searchParams, setToken, setUser]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 to-blue-800 flex items-center justify-center px-4">
      <div className="bg-white rounded-lg shadow-xl p-8 w-full max-w-sm text-center">
        <Loader className="animate-spin text-blue-600 mx-auto mb-4" size={32} />
        <p className="text-gray-700 font-medium">Completing sign in...</p>
      </div>
    </div>
  );
};

export default OAuthCallbackPage;
