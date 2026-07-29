import React, {
  useEffect,
  useRef,
  useState,
} from 'react';

import api from '../api';

function NotificationBell() {
  const containerRef = useRef(null);

  const [notifications, setNotifications] =
    useState([]);

  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const unreadCount = notifications.filter(
    (notification) => !notification.is_read,
  ).length;

  const fetchNotifications = async (
    showLoading = false,
  ) => {
    if (showLoading) {
      setLoading(true);
    }

    try {
      const response = await api.get(
        '/notifications',
      );

      setNotifications(response.data);
    } catch (error) {
      console.error(
        (
          'Erreur lors du chargement ' +
          'des notifications :'
        ),
        error,
      );
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchNotifications(true);

    /*
     * Actualisation automatique toutes les 10 secondes.
     */
    const intervalId = window.setInterval(() => {
      fetchNotifications(false);
    }, 10000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener(
      'mousedown',
      handleOutsideClick,
    );

    return () => {
      document.removeEventListener(
        'mousedown',
        handleOutsideClick,
      );
    };
  }, []);

  const markAsRead = async (notification) => {
    if (notification.is_read) {
      return;
    }

    try {
      await api.patch(
        `/notifications/${notification.id}/read`,
      );

      setNotifications(
        (currentNotifications) =>
          currentNotifications.map(
            (currentNotification) =>
              currentNotification.id
              === notification.id
                ? {
                    ...currentNotification,
                    is_read: true,
                  }
                : currentNotification,
          ),
      );
    } catch (error) {
      console.error(
        (
          'Erreur lors de la lecture ' +
          'de la notification :'
        ),
        error,
      );
    }
  };

  const handleNotificationClick = async (
    notification,
  ) => {
    await markAsRead(notification);

    setIsOpen(false);

    if (
      notification.notification_type
      === 'new_account'
    ) {
      window.location.assign('/admin/users');
      return;
    }

    if (
      notification.notification_type
      === 'invoice_to_validate'
    ) {
      window.location.assign('/lots');
    }
  };

  const markAllAsRead = async () => {
    try {
      await api.patch(
        '/notifications/read-all',
      );

      setNotifications(
        (currentNotifications) =>
          currentNotifications.map(
            (notification) => ({
              ...notification,
              is_read: true,
            }),
          ),
      );
    } catch (error) {
      console.error(
        (
          'Erreur lors de la lecture ' +
          'des notifications :'
        ),
        error,
      );
    }
  };

  const formatDate = (dateValue) =>
    new Date(dateValue).toLocaleString(
      'fr-FR',
      {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      },
    );

  return (
    <div
      ref={containerRef}
      className="relative"
    >
      <button
        type="button"
        onClick={() => {
          setIsOpen(
            (currentValue) => !currentValue,
          );

          if (!isOpen) {
            fetchNotifications(false);
          }
        }}
        className="
          relative w-10 h-10
          flex items-center justify-center
          rounded-full bg-gray-100
          hover:bg-gray-200
          transition-colors
        "
        title="Notifications"
      >
        <span className="text-xl">
          🔔
        </span>

        {unreadCount > 0 && (
          <span
            className="
              absolute -top-1 -right-1
              min-w-5 h-5 px-1
              flex items-center justify-center
              rounded-full bg-red-500
              text-white text-[10px]
              font-bold border-2 border-white
            "
          >
            {unreadCount > 99
              ? '99+'
              : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className="
            absolute right-0 mt-3
            w-96 max-w-[90vw]
            bg-white
            border border-gray-200
            rounded-xl shadow-xl
            z-50 overflow-hidden
          "
        >
          <div
            className="
              flex items-center justify-between
              px-4 py-3 border-b bg-gray-50
            "
          >
            <div>
              <h3
                className="
                  font-semibold text-gray-800
                "
              >
                Notifications
              </h3>

              <p className="text-xs text-gray-400">
                {unreadCount} non lue(s)
              </p>
            </div>

            {unreadCount > 0 && (
              <button
                type="button"
                onClick={markAllAsRead}
                className="
                  text-xs font-medium
                  text-blue-600
                  hover:text-blue-800
                "
              >
                Tout marquer comme lu
              </button>
            )}
          </div>

          <div
            className="
              max-h-96 overflow-y-auto
            "
          >
            {loading ? (
              <p
                className="
                  py-8 text-center
                  text-sm text-gray-400
                "
              >
                Chargement...
              </p>
            ) : notifications.length === 0 ? (
              <div className="py-10 text-center">
                <div className="text-3xl mb-2">
                  🔕
                </div>

                <p className="text-sm text-gray-400">
                  Aucune notification.
                </p>
              </div>
            ) : (
              notifications.map(
                (notification) => (
                  <button
                    type="button"
                    key={notification.id}
                    onClick={() =>
                      handleNotificationClick(
                        notification,
                      )
                    }
                    className={`
                      w-full text-left
                      px-4 py-3 border-b
                      border-gray-100
                      hover:bg-blue-50/50
                      transition-colors
                      ${
                        notification.is_read
                          ? 'bg-white'
                          : 'bg-blue-50/40'
                      }
                    `}
                  >
                    <div className="flex gap-3">
                      <span
                        className="
                          text-xl shrink-0
                        "
                      >
                        {
                          notification
                            .notification_type
                          === 'new_account'
                            ? '👤'
                            : '📄'
                        }
                      </span>

                      <div
                        className="
                          min-w-0 flex-1
                        "
                      >
                        <div
                          className="
                            flex items-start
                            justify-between gap-2
                          "
                        >
                          <p
                            className="
                              text-sm font-semibold
                              text-gray-800
                            "
                          >
                            {notification.title}
                          </p>

                          {!notification.is_read && (
                            <span
                              className="
                                w-2 h-2 mt-1.5
                                rounded-full
                                bg-blue-600 shrink-0
                              "
                            />
                          )}
                        </div>

                        <p
                          className="
                            text-xs text-gray-600
                            mt-1 leading-5
                          "
                        >
                          {notification.message}
                        </p>

                        <p
                          className="
                            text-[11px]
                            text-gray-400 mt-2
                          "
                        >
                          {formatDate(
                            notification.created_at,
                          )}
                        </p>
                      </div>
                    </div>
                  </button>
                ),
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default NotificationBell;