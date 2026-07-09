import React, { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import api from '../api';

function AdminRoute({ children }) {
  const [status, setStatus] = useState('loading'); // loading | authorized | unauthorized

  useEffect(() => {
    const checkRole = async () => {
      try {
        const response = await api.get('/users/me');
        if (response.data.role === 'admin') {
          setStatus('authorized');
        } else {
          setStatus('unauthorized');
        }
      } catch (err) {
        setStatus('unauthorized');
      }
    };
    checkRole();
  }, []);

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-500">Vérification des accès...</p>
      </div>
    );
  }

  if (status === 'unauthorized') {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}

export default AdminRoute;