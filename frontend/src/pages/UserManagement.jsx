import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import NotificationBell from '../components/NotificationBell';

function UserManagement() {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoadingId, setActionLoadingId] = useState(null);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/users');
      setUsers(response.data);
    } catch (err) {
      setError("Impossible de charger la liste des utilisateurs.");
    } finally {
      setLoading(false);
    }
  };

  const handleRoleChange = async (userId, newRole) => {
    setActionLoadingId(userId);
    setError('');
    try {
      await api.patch(`/users/${userId}/role`, { role: newRole });
      fetchUsers();
    } catch (err) {
      setError(err.response?.data?.detail || "Erreur lors du changement de rôle.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleStatusChange = async (userId, newStatus) => {
    setActionLoadingId(userId);
    setError('');
    try {
      await api.patch(`/users/${userId}/status`, { status: newStatus });
      fetchUsers();
    } catch (err) {
      setError(err.response?.data?.detail || "Erreur lors du changement de statut.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDelete = async (userId, email) => {
    if (!window.confirm(`Confirmer la suppression de ${email} ?`)) return;

    setActionLoadingId(userId);
    setError('');
    try {
      await api.delete(`/users/${userId}`);
      fetchUsers();
    } catch (err) {
      setError(err.response?.data?.detail || "Erreur lors de la suppression.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const roleBadgeColor = (role) => {
    switch (role) {
      case 'admin': return 'bg-red-100 text-red-700 border-red-200';
      case 'comptable': return 'bg-blue-100 text-blue-700 border-blue-200';
      default: return 'bg-gray-100 text-gray-700 border-gray-200';
    }
  };

  const statusBadgeColor = (status) => {
    switch (status) {
      case 'active': return 'bg-green-100 text-green-700 border-green-200';
      case 'suspended': return 'bg-red-100 text-red-700 border-red-200';
      default: return 'bg-amber-100 text-amber-700 border-amber-200'; // pending
    }
  };

  const statusLabel = (status) => {
    switch (status) {
      case 'active': return 'Actif';
      case 'suspended': return 'Suspendu';
      default: return 'En attente';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <h1 className="text-xl font-bold text-blue-600">OCR Accounting Platform 🚀</h1>
            <div className="flex gap-3">
              <NotificationBell />
              <button
                onClick={() => navigate('/dashboard')}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
              >
                ← Retour au tableau de bord
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-6xl w-full mx-auto py-10 px-4 sm:px-6 lg:px-8">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-2xl font-semibold text-gray-800 mb-2">Gestion des utilisateurs</h2>
          <p className="text-gray-600 mb-6">Administrez les comptes, les rôles et les statuts des utilisateurs de la plateforme.</p>

          {error && (
            <div className="mb-4 p-3 bg-red-50 text-red-600 border border-red-200 rounded-md text-sm">
              {error}
            </div>
          )}

          {loading ? (
            <p className="text-gray-400 text-center py-10">Chargement...</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 text-gray-500 uppercase text-xs">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Nom complet</th>
                    <th className="px-4 py-3">Email</th>
                    <th className="px-4 py-3">Téléphone</th>
                    <th className="px-4 py-3">Rôle</th>
                    <th className="px-4 py-3">Statut</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id} className="border-b border-gray-100 hover:bg-gray-50/50 align-top">
                      <td className="px-4 py-3 text-gray-500">{user.id}</td>
                      <td className="px-4 py-3 font-medium text-gray-700">{user.first_name} {user.last_name}</td>
                      <td className="px-4 py-3 text-gray-600">{user.email}</td>
                      <td className="px-4 py-3 text-gray-600">{user.phone_number}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-2">
                          <span className={`inline-block w-fit px-2 py-1 rounded-full text-xs font-medium border ${roleBadgeColor(user.role)}`}>
                            {user.role}
                          </span>
                          <select
                            value={user.role}
                            onChange={(e) => handleRoleChange(user.id, e.target.value)}
                            disabled={actionLoadingId === user.id}
                            className="border border-gray-300 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                          >
                            <option value="user">Utilisateur</option>
                            <option value="comptable">Comptable</option>
                            <option value="admin">Administrateur</option>
                          </select>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-2">
                          <span className={`inline-block w-fit px-2 py-1 rounded-full text-xs font-medium border ${statusBadgeColor(user.status)}`}>
                            {statusLabel(user.status)}
                          </span>
                          <select
                            value={user.status}
                            onChange={(e) => handleStatusChange(user.id, e.target.value)}
                            disabled={actionLoadingId === user.id}
                            className="border border-gray-300 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                          >
                            <option value="pending">En attente</option>
                            <option value="active">Actif</option>
                            <option value="suspended">Suspendu</option>
                          </select>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => handleDelete(user.id, user.email)}
                          disabled={actionLoadingId === user.id}
                          className="text-red-600 hover:text-red-800 text-sm font-medium disabled:opacity-50"
                        >
                          Supprimer
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default UserManagement;