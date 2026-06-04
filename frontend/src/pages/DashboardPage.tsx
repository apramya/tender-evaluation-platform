import React from 'react';
import { Link } from 'react-router-dom';
import { FileText, Users, CheckCircle, ClipboardList, Trash2 } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import apiService from '../services/apiService';
import { useAuthStore } from '../store/authStore';

interface DashboardCard {
  title: string;
  value: number;
  icon: React.ReactNode;
  href: string;
  color: string;
}

const DashboardPage: React.FC = () => {
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const canManageTenders = user?.role === 'admin' || user?.role === 'procurement_officer' || user?.role === 'user';
  const canDeleteTenders = user?.role === 'admin';
  const canReview = user?.role === 'admin' || user?.role === 'procurement_officer';

  // Fetch tenders
  const { data: tendersData } = useQuery({
    queryKey: ['tenders'],
    queryFn: () => apiService.listTenders(0, 100),
  });

  // Fetch evaluations
  const { data: evaluationsData } = useQuery({
    queryKey: ['evaluations'],
    queryFn: () => apiService.listEvaluations(undefined, undefined, 0, 100),
  });

  const { data: biddersData } = useQuery({
    queryKey: ['bidders'],
    queryFn: () => apiService.listBidders(undefined, 0, 100),
  });

  const { data: reviewQueueData } = useQuery({
    queryKey: ['review-queue'],
    queryFn: () => apiService.getReviewQueue(0, 100),
    enabled: canReview,
  });

  const tenderCount = tendersData?.total || 0;
  const evaluationCount = evaluationsData?.total || 0;
  const bidderCount = biddersData?.total || 0;
  const reviewQueueCount = reviewQueueData?.total || reviewQueueData?.items?.length || 0;

  const handleDeleteTender = async (tenderId: string) => {
    if (!window.confirm('Delete this tender and related bidders/evaluations?')) {
      return;
    }
    try {
      await apiService.deleteTender(tenderId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tenders'] }),
        queryClient.invalidateQueries({ queryKey: ['evaluations'] }),
        queryClient.invalidateQueries({ queryKey: ['bidders'] }),
      ]);
      toast.success('Tender deleted');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not delete tender');
    }
  };

  const handleDeleteBidder = async (bidderId: string) => {
    if (!window.confirm('Delete this bidder, uploaded documents, evaluations and reviews?')) {
      return;
    }
    try {
      await apiService.deleteBidder(bidderId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['bidders'] }),
        queryClient.invalidateQueries({ queryKey: ['evaluations'] }),
        queryClient.invalidateQueries({ queryKey: ['review-queue'] }),
      ]);
      toast.success('Bidder deleted');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not delete bidder');
    }
  };

  const cards: DashboardCard[] = [
    ...(canManageTenders ? [{
      title: 'Tenders',
      value: tenderCount,
      icon: <FileText size={32} />,
      href: '/tenders',
      color: 'bg-blue-500',
    }] : []),
    {
      title: 'Evaluations',
      value: evaluationCount,
      icon: <CheckCircle size={32} />,
      href: '/evaluations',
      color: 'bg-green-500',
    },
    {
      title: 'Upload Bidder',
      value: bidderCount,
      icon: <Users size={32} />,
      href: '/bidder/upload',
      color: 'bg-purple-500',
    },
    ...(canReview ? [{
      title: 'Review Queue',
      value: reviewQueueCount,
      icon: <ClipboardList size={32} />,
      href: '/review-queue',
      color: 'bg-orange-500',
    }] : []),
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Dashboard</h1>
          <p className="text-gray-600">Welcome to the Tender Evaluation Platform</p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {cards.map((card) => (
            <Link
              key={card.title}
              to={card.href}
              className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition cursor-pointer"
            >
              <div className={`${card.color} text-white rounded-lg p-3 w-fit mb-4`}>
                {card.icon}
              </div>
              <h3 className="text-gray-600 text-sm font-medium">{card.title}</h3>
              <p className="text-3xl font-bold text-gray-900 mt-2">{card.value}</p>
            </Link>
          ))}
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recent Tenders */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Recent Tenders</h2>
            {tendersData?.tenders && tendersData.tenders.length > 0 ? (
              <div className="space-y-3">
                {tendersData.tenders.slice(0, 5).map((tender: any) => (
                  <div
                    key={tender.id}
                    className="p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-gray-900 truncate">{tender.title}</p>
                      <p className="text-xs text-gray-500">{tender.tender_number}</p>
                    </div>
                    {canDeleteTenders && (
                      <button
                        type="button"
                        onClick={() => handleDeleteTender(tender.id)}
                        className="shrink-0 rounded-md p-2 text-red-600 hover:bg-red-50"
                        title="Delete tender"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500">
                {canManageTenders ? 'No tenders yet. Start by uploading a tender.' : 'No tenders are available yet.'}
              </p>
            )}
          </div>

          {/* Available Bidders */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Available Bidders</h2>
            {biddersData?.bidders && biddersData.bidders.length > 0 ? (
              <div className="space-y-3">
                {biddersData.bidders.slice(0, 6).map((bidder: any) => (
                  <div
                    key={bidder.id}
                    className="rounded-lg bg-gray-50 p-3 hover:bg-gray-100 flex items-center justify-between gap-3"
                  >
                    <Link to="/evaluations" className="min-w-0 flex-1">
                      <p className="font-medium text-gray-900 truncate">{bidder.company_name}</p>
                      <p className="text-xs text-gray-500 truncate">
                        {bidder.gst_number || bidder.pan_number || bidder.contact_email || bidder.id}
                      </p>
                    </Link>
                    <button
                      type="button"
                      onClick={() => handleDeleteBidder(bidder.id)}
                      className="shrink-0 rounded-md p-2 text-red-600 hover:bg-red-50"
                      title="Delete bidder"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500">No bidder submissions are available yet.</p>
            )}
          </div>

          {/* Quick Links */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Quick Actions</h2>
            <div className="space-y-2">
              {canManageTenders && (
                <Link
                  to="/tender/upload"
                  className="block w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 transition text-center"
                >
                  Upload Tender
                </Link>
              )}
              <Link
                to="/bidder/upload"
                className="block w-full bg-green-600 text-white py-2 rounded-lg font-medium hover:bg-green-700 transition text-center"
              >
                Submit Bidder Proposal
              </Link>
              <Link
                to="/evaluations"
                className="block w-full bg-purple-600 text-white py-2 rounded-lg font-medium hover:bg-purple-700 transition text-center"
              >
                View Evaluations
              </Link>
              {canReview && (
                <Link
                  to="/review-queue"
                  className="block w-full bg-orange-600 text-white py-2 rounded-lg font-medium hover:bg-orange-700 transition text-center"
                >
                  Review Queue
                </Link>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;
