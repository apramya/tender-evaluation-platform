import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ClipboardList, Loader, UserCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import apiService from '../services/apiService';

const ReviewQueuePage: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState('');
  const [assigneeId, setAssigneeId] = useState('');
  const [decision, setDecision] = useState('needs_manual_review');
  const [comments, setComments] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['review-queue'],
    queryFn: () => apiService.getReviewQueue(0, 50),
  });

  const { data: assigneesData } = useQuery({
    queryKey: ['review-assignees'],
    queryFn: () => apiService.listReviewAssignees(),
  });

  const items = data?.items || [];
  const activeItem = items.find((item: any) => item.id === activeId) || items[0];
  const assignees = assigneesData?.users || [];
  const assigneeMap = assignees.reduce((map: Record<string, any>, user: any) => {
    map[user.id] = user;
    return map;
  }, {});

  const handleAssign = async (queueId: string) => {
    try {
      await apiService.assignReviewToMe(queueId);
      await queryClient.invalidateQueries({ queryKey: ['review-queue'] });
      toast.success('Review assigned');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Could not assign review');
    }
  };

  const handleAssignToUser = async () => {
    if (!activeItem || !assigneeId) {
      toast.error('Select a reviewer to assign');
      return;
    }

    try {
      await apiService.assignReview(activeItem.id, assigneeId);
      await queryClient.invalidateQueries({ queryKey: ['review-queue'] });
      toast.success('Review assigned');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Could not assign review');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeItem) return;

    try {
      setSubmitting(true);
      await apiService.submitReview(activeItem.evaluation_id, decision, comments, decision !== 'needs_manual_review');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['review-queue'] }),
        queryClient.invalidateQueries({ queryKey: ['evaluations'] }),
      ]);
      setComments('');
      toast.success('Review submitted');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Could not submit review');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-6xl mx-auto px-4">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Review Queue</h1>
          <p className="text-gray-600 mt-2">Assign pending evaluations and record manual decisions.</p>
        </div>

        {isLoading ? (
          <div className="bg-white rounded-lg shadow-md p-10 flex items-center justify-center gap-3 text-gray-600">
            <Loader className="animate-spin" size={22} />
            Loading review queue...
          </div>
        ) : error ? (
          <div className="bg-white rounded-lg shadow-md p-8">
            <p className="text-red-700">Unable to load review queue. This page requires procurement officer or admin access.</p>
          </div>
        ) : items.length === 0 ? (
          <div className="bg-white rounded-lg shadow-md p-10 text-center">
            <ClipboardList size={44} className="text-gray-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-gray-900">No pending reviews</h2>
            <p className="text-gray-600 mt-1">Evaluations that need manual review will appear here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="bg-white rounded-lg shadow-md divide-y divide-gray-200 overflow-hidden">
              {items.map((item: any) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveId(item.id)}
                  className={`w-full text-left p-4 hover:bg-gray-50 ${activeItem?.id === item.id ? 'bg-blue-50' : ''}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-gray-900 truncate">{item.reason.replace(/_/g, ' ')}</p>
                      <p className="text-xs text-gray-500 truncate">{item.evaluation_id}</p>
                    </div>
                    <span className="rounded-full bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800">
                      P{item.priority}
                    </span>
                  </div>
                </button>
              ))}
            </div>

            <form onSubmit={handleSubmit} className="lg:col-span-2 bg-white rounded-lg shadow-md p-6">
              <div className="border-b border-gray-200 pb-5 mb-5">
                <h2 className="text-xl font-bold text-gray-900">Manual Review</h2>
                <p className="text-sm text-gray-500 mt-1">{activeItem.evaluation_id}</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                  <p className="text-sm text-gray-500">Status</p>
                  <p className="font-semibold text-gray-900 capitalize">{activeItem.status.replace(/_/g, ' ')}</p>
                </div>
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                  <p className="text-sm text-gray-500">Reason</p>
                  <p className="font-semibold text-gray-900 capitalize">{activeItem.reason.replace(/_/g, ' ')}</p>
                </div>
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 md:col-span-2">
                  <p className="text-sm text-gray-500">Assigned to</p>
                  <p className="font-semibold text-gray-900">
                    {activeItem.assigned_to
                      ? assigneeMap[activeItem.assigned_to]?.full_name || activeItem.assigned_to
                      : 'Unassigned'}
                  </p>
                </div>
              </div>

              <div className="mb-5 grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-3">
                <select
                  value={assigneeId}
                  onChange={(e) => setAssigneeId(e.target.value)}
                  className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                >
                  <option value="">Select reviewer/officer</option>
                  {assignees.map((user: any) => (
                    <option key={user.id} value={user.id}>
                      {user.full_name} ({user.role.replace(/_/g, ' ')})
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleAssignToUser}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-200 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50"
                >
                  <UserCheck size={16} />
                  Assign
                </button>
                <button
                  type="button"
                  onClick={() => handleAssign(activeItem.id)}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  <UserCheck size={16} />
                  Assign to me
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label htmlFor="decision" className="block text-sm font-medium text-gray-700 mb-1">
                    Decision
                  </label>
                  <select
                    id="decision"
                    value={decision}
                    onChange={(e) => setDecision(e.target.value)}
                    className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  >
                    <option value="eligible">Eligible</option>
                    <option value="not_eligible">Not eligible</option>
                    <option value="needs_manual_review">Needs manual review</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="comments" className="block text-sm font-medium text-gray-700 mb-1">
                    Comments
                  </label>
                  <textarea
                    id="comments"
                    value={comments}
                    onChange={(e) => setComments(e.target.value)}
                    rows={5}
                    className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                    placeholder="Record the reason for your decision"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="mt-6 w-full rounded-lg bg-blue-600 py-3 font-medium text-white hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {submitting ? <Loader className="animate-spin" size={20} /> : <Check size={20} />}
                Submit Review
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReviewQueuePage;
