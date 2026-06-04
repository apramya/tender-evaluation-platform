import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LogOut, Menu, X, FileText, Users, CheckCircle, ClipboardList, History, Shield } from 'lucide-react';
import { useAuthStore } from '../store/authStore';

const Navigation: React.FC = () => {
  const [isOpen, setIsOpen] = React.useState(false);
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const canManageTenders = user?.role === 'admin' || user?.role === 'procurement_officer' || user?.role === 'user';
  const canReview = user?.role === 'admin' || user?.role === 'procurement_officer';
  const isAdmin = user?.role === 'admin';

  const navLinks = [
    { href: '/', label: 'Dashboard', icon: <FileText size={20} /> },
    ...(canManageTenders
      ? [{ href: '/tenders', label: 'Tenders', icon: <FileText size={20} /> }]
      : []),
    { href: '/bidder/upload', label: 'Bidder Submissions', icon: <Users size={20} /> },
    { href: '/evaluations', label: 'Evaluations', icon: <CheckCircle size={20} /> },
    ...(canReview
      ? [{ href: '/review-queue', label: 'Review Queue', icon: <ClipboardList size={20} /> }]
      : []),
    ...(isAdmin
      ? [{ href: '/audit-logs', label: 'Audit Logs', icon: <History size={20} /> }]
      : []),
    ...(isAdmin
      ? [{ href: '/admin/users', label: 'Admin', icon: <Shield size={20} /> }]
      : []),
  ];

  return (
    <nav className="bg-white shadow-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex justify-between items-center h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center space-x-2 font-bold text-lg text-blue-600">
            <FileText size={28} />
            <span>TenderEval</span>
          </Link>

          {/* Desktop Menu */}
          <div className="hidden xl:flex items-center space-x-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                to={link.href}
                className="flex items-center space-x-1 px-2 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100 transition"
              >
                {link.icon}
                <span>{link.label}</span>
              </Link>
            ))}
          </div>

          {/* User Menu */}
          <div className="flex items-center space-x-4">
            <div className="hidden xl:flex items-center space-x-2">
              <div className="text-right">
                <p className="text-sm font-medium text-gray-900">{user?.full_name}</p>
                <p className="text-xs text-gray-500">{user?.role}</p>
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="flex items-center space-x-2 px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition"
            >
              <LogOut size={18} />
              <span className="hidden sm:inline">Logout</span>
            </button>

            {/* Mobile Menu Toggle */}
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="xl:hidden p-2 rounded-md text-gray-700 hover:bg-gray-100"
            >
              {isOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {/* Mobile Menu */}
        {isOpen && (
          <div className="xl:hidden pb-4 space-y-2">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                to={link.href}
                onClick={() => setIsOpen(false)}
                className="flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100 transition block"
              >
                {link.icon}
                <span>{link.label}</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </nav>
  );
};

export default Navigation;
