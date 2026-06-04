import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Edit2, Loader, Plus, Save, Trash2, UserCheck, UserX, X } from 'lucide-react';
import toast from 'react-hot-toast';
import apiService from '../services/apiService';
import { useAuthStore } from '../store/authStore';

const roles = ['user', 'procurement_officer', 'admin'];

const AdminUsersPage: React.FC = () => {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((state) => state.user);
  const [updatingId, setUpdatingId] = useState('');
  const [deletingId, setDeletingId] = useState('');
  const [editingId, setEditingId] = useState('');
  const [editUser, setEditUser] = useState<any>(null);
  const [creating, setCreating] = useState(false);
  const [newUser, setNewUser] = useState({
    full_name: '',
    email: '',
    password: '',
    organization: '',
    role: 'user',
    is_active: true,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => apiService.listUsers(0, 100),
  });

  const users = data?.users || [];

  const updateUser = async (userId: string, updateData: any) => {
    try {
      setUpdatingId(userId);
      await apiService.updateUser(userId, updateData);
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      toast.success('User updated');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Could not update user');
    } finally {
      setUpdatingId('');
    }
  };

  const startEditing = (user: any) => {
    setEditingId(user.id);
    setEditUser({
      full_name: user.full_name || '',
      email: user.email || '',
      organization: user.organization || '',
      role: user.role || 'user',
      is_active: user.is_active,
      password: '',
    });
  };

  const cancelEditing = () => {
    setEditingId('');
    setEditUser(null);
  };

  const saveEditedUser = async (userId: string) => {
    if (!editUser?.full_name || !editUser?.email) {
      toast.error('Name and email are required');
      return;
    }
    if (editUser.password && editUser.password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    const payload = {
      full_name: editUser.full_name,
      email: editUser.email,
      organization: editUser.organization || null,
      role: editUser.role,
      is_active: editUser.is_active,
      ...(editUser.password ? { password: editUser.password } : {}),
    };
    await updateUser(userId, payload);
    cancelEditing();
  };

  const deleteUser = async (user: any) => {
    if (user.id === currentUser?.id) {
      toast.error('You cannot delete your own account');
      return;
    }
    if (!window.confirm(`Delete ${user.full_name}? Their audit history will be preserved.`)) {
      return;
    }
    try {
      setDeletingId(user.id);
      await apiService.deleteUser(user.id);
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      toast.success('User deleted');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Could not delete user');
    } finally {
      setDeletingId('');
    }
  };

  const createUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUser.full_name || !newUser.email || !newUser.password) {
      toast.error('Name, email and password are required');
      return;
    }
    if (newUser.password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    try {
      setCreating(true);
      await apiService.createUser({
        ...newUser,
        organization: newUser.organization || null,
      });
      setNewUser({
        full_name: '',
        email: '',
        password: '',
        organization: '',
        role: 'user',
        is_active: true,
      });
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      toast.success('User created');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Could not create user');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-6 sm:py-8">
      <div className="max-w-7xl mx-auto px-3 sm:px-4">
        <div className="mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Admin Users</h1>
          <p className="text-gray-600 mt-2">Manage user roles and account access.</p>
        </div>

        <form onSubmit={createUser} className="bg-white rounded-lg shadow-md p-4 sm:p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Plus size={20} className="text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900">Create user</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-4">
            <input
              type="text"
              value={newUser.full_name}
              onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })}
              className="rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 xl:col-span-2"
              placeholder="Full name"
              disabled={creating}
            />
            <input
              type="email"
              value={newUser.email}
              onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
              className="rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 xl:col-span-2"
              placeholder="Email"
              disabled={creating}
            />
            <input
              type="password"
              value={newUser.password}
              onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
              className="rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              placeholder="Password"
              disabled={creating}
            />
            <select
              value={newUser.role}
              onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
              className="rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              disabled={creating}
            >
              {roles.map((role) => (
                <option key={role} value={role}>
                  {role.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
            <input
              type="text"
              value={newUser.organization}
              onChange={(e) => setNewUser({ ...newUser, organization: e.target.value })}
              className="rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 md:col-span-2 xl:col-span-2"
              placeholder="Organization"
              disabled={creating}
            />
            <label className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2">
              <input
                type="checkbox"
                checked={newUser.is_active}
                onChange={(e) => setNewUser({ ...newUser, is_active: e.target.checked })}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                disabled={creating}
              />
              <span className="text-sm text-gray-700">Active</span>
            </label>
            <button
              type="submit"
              disabled={creating}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {creating ? <Loader size={18} className="animate-spin" /> : <Plus size={18} />}
              Create
            </button>
          </div>
        </form>

        {isLoading ? (
          <div className="bg-white rounded-lg shadow-md p-10 flex items-center justify-center gap-3 text-gray-600">
            <Loader className="animate-spin" size={22} />
            Loading users...
          </div>
        ) : error ? (
          <div className="bg-white rounded-lg shadow-md p-8 text-red-700">
            Admin access is required to manage users.
          </div>
        ) : (
          <>
          <div className="hidden md:block bg-white rounded-lg shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">User</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Organization</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Role</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Status</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase text-gray-500">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {users.map((user: any) => (
                    <tr key={user.id}>
                      <td className="px-4 py-3 min-w-[260px]">
                        {editingId === user.id ? (
                          <div className="space-y-2">
                            <input
                              type="text"
                              value={editUser.full_name}
                              onChange={(e) => setEditUser({ ...editUser, full_name: e.target.value })}
                              className="w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                              placeholder="Full name"
                            />
                            <input
                              type="email"
                              value={editUser.email}
                              onChange={(e) => setEditUser({ ...editUser, email: e.target.value })}
                              className="w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                              placeholder="Email"
                            />
                          </div>
                        ) : (
                          <>
                            <p className="font-medium text-gray-900">{user.full_name}</p>
                            <p className="text-sm text-gray-500">{user.email}</p>
                          </>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700 min-w-[180px]">
                        {editingId === user.id ? (
                          <input
                            type="text"
                            value={editUser.organization}
                            onChange={(e) => setEditUser({ ...editUser, organization: e.target.value })}
                            className="w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                            placeholder="Organization"
                          />
                        ) : (
                          user.organization || '-'
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={editingId === user.id ? editUser.role : user.role}
                          onChange={(e) => {
                            if (editingId === user.id) {
                              setEditUser({ ...editUser, role: e.target.value });
                            } else {
                              updateUser(user.id, { role: e.target.value });
                            }
                          }}
                          className="rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                          disabled={updatingId === user.id}
                        >
                          {roles.map((role) => (
                            <option key={role} value={role}>
                              {role.replace(/_/g, ' ')}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        {editingId === user.id ? (
                          <label className="inline-flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={editUser.is_active}
                              onChange={(e) => setEditUser({ ...editUser, is_active: e.target.checked })}
                              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                              disabled={user.id === currentUser?.id}
                            />
                            <span className="text-sm text-gray-700">Active</span>
                          </label>
                        ) : (
                          <span
                            className={`rounded-full px-2 py-1 text-xs font-medium ${
                              user.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                            }`}
                          >
                            {user.is_active ? 'Active' : 'Inactive'}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right min-w-[260px]">
                        {editingId === user.id && (
                          <input
                            type="password"
                            value={editUser.password}
                            onChange={(e) => setEditUser({ ...editUser, password: e.target.value })}
                            className="mb-2 w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                            placeholder="New password optional"
                          />
                        )}
                        <div className="flex flex-wrap justify-end gap-2">
                          {editingId === user.id ? (
                            <>
                              <button
                                type="button"
                                onClick={() => saveEditedUser(user.id)}
                                disabled={updatingId === user.id}
                                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                              >
                                {updatingId === user.id ? <Loader size={16} className="animate-spin" /> : <Save size={16} />}
                                Save
                              </button>
                              <button
                                type="button"
                                onClick={cancelEditing}
                                className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                              >
                                <X size={16} />
                                Cancel
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                type="button"
                                onClick={() => startEditing(user)}
                                className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                              >
                                <Edit2 size={16} />
                                Edit
                              </button>
                              <button
                                type="button"
                                onClick={() => updateUser(user.id, { is_active: !user.is_active })}
                                disabled={updatingId === user.id || user.id === currentUser?.id}
                                className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                              >
                                {updatingId === user.id ? (
                                  <Loader size={16} className="animate-spin" />
                                ) : user.is_active ? (
                                  <UserX size={16} />
                                ) : (
                                  <UserCheck size={16} />
                                )}
                                {user.is_active ? 'Deactivate' : 'Activate'}
                              </button>
                              <button
                                type="button"
                                onClick={() => deleteUser(user)}
                                disabled={deletingId === user.id || user.id === currentUser?.id}
                                className="inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                              >
                                {deletingId === user.id ? <Loader size={16} className="animate-spin" /> : <Trash2 size={16} />}
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="md:hidden space-y-3">
            {users.map((user: any) => (
              <div key={user.id} className="bg-white rounded-lg shadow-md p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    {editingId === user.id ? (
                      <div className="space-y-2">
                        <input
                          type="text"
                          value={editUser.full_name}
                          onChange={(e) => setEditUser({ ...editUser, full_name: e.target.value })}
                          className="w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                          placeholder="Full name"
                        />
                        <input
                          type="email"
                          value={editUser.email}
                          onChange={(e) => setEditUser({ ...editUser, email: e.target.value })}
                          className="w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                          placeholder="Email"
                        />
                      </div>
                    ) : (
                      <>
                        <p className="font-medium text-gray-900 truncate">{user.full_name}</p>
                        <p className="text-sm text-gray-500 truncate">{user.email}</p>
                        <p className="text-sm text-gray-600 mt-1">{user.organization || '-'}</p>
                      </>
                    )}
                  </div>
                  {editingId !== user.id && (
                    <span
                      className={`shrink-0 rounded-full px-2 py-1 text-xs font-medium ${
                        user.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {user.is_active ? 'Active' : 'Inactive'}
                    </span>
                  )}
                </div>
                <div className="mt-4 grid grid-cols-1 gap-3">
                  {editingId === user.id && (
                    <>
                      <input
                        type="text"
                        value={editUser.organization}
                        onChange={(e) => setEditUser({ ...editUser, organization: e.target.value })}
                        className="w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                        placeholder="Organization"
                      />
                      <input
                        type="password"
                        value={editUser.password}
                        onChange={(e) => setEditUser({ ...editUser, password: e.target.value })}
                        className="w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                        placeholder="New password optional"
                      />
                    </>
                  )}
                  <select
                    value={editingId === user.id ? editUser.role : user.role}
                    onChange={(e) => {
                      if (editingId === user.id) {
                        setEditUser({ ...editUser, role: e.target.value });
                      } else {
                        updateUser(user.id, { role: e.target.value });
                      }
                    }}
                    className="w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                    disabled={updatingId === user.id}
                  >
                    {roles.map((role) => (
                      <option key={role} value={role}>
                        {role.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                  {editingId === user.id ? (
                    <>
                      <label className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2">
                        <input
                          type="checkbox"
                          checked={editUser.is_active}
                          onChange={(e) => setEditUser({ ...editUser, is_active: e.target.checked })}
                          className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          disabled={user.id === currentUser?.id}
                        />
                        <span className="text-sm text-gray-700">Active</span>
                      </label>
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => saveEditedUser(user.id)}
                          disabled={updatingId === user.id}
                          className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                          {updatingId === user.id ? <Loader size={16} className="animate-spin" /> : <Save size={16} />}
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={cancelEditing}
                          className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                        >
                          <X size={16} />
                          Cancel
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="grid grid-cols-1 gap-2">
                      <button
                        type="button"
                        onClick={() => startEditing(user)}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                      >
                        <Edit2 size={16} />
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => updateUser(user.id, { is_active: !user.is_active })}
                        disabled={updatingId === user.id || user.id === currentUser?.id}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                      >
                        {updatingId === user.id ? (
                          <Loader size={16} className="animate-spin" />
                        ) : user.is_active ? (
                          <UserX size={16} />
                        ) : (
                          <UserCheck size={16} />
                        )}
                        {user.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteUser(user)}
                        disabled={deletingId === user.id || user.id === currentUser?.id}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                      >
                        {deletingId === user.id ? <Loader size={16} className="animate-spin" /> : <Trash2 size={16} />}
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          </>
        )}
      </div>
    </div>
  );
};

export default AdminUsersPage;
