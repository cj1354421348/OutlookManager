/**
 * TimeUtils - Unified Time Handling for Outlook Manager
 * 
 * All time display and generation must go through this utility.
 */
class TimeUtils {
    // static TIMEZONE = 'Asia/Shanghai'; // Removed strict enforcement

    static timeOffset = 0; // Server time minus Local time (ms)

    /**
     * Initialize TimeUtils with server time
     * @param {number} serverTimestamp - Server timestamp in seconds (float)
     */
    static init(serverTimestamp) {
        if (!serverTimestamp) return;
        const nowMs = Date.now();
        const serverMs = serverTimestamp * 1000;
        this.timeOffset = serverMs - nowMs;
        console.log(`[TimeUtils] Synced with server. Offset: ${this.timeOffset}ms`);
    }

    /**
     * Get current time as Date object (Synchronized with Server)
     */
    static now() {
        return new Date(Date.now() + this.timeOffset);
    }

    /**
     * Get current timestamp in seconds (float), synchronized
     */
    static timestamp() {
        return (Date.now() + this.timeOffset) / 1000;
    }

    /**
     * Parse ISO date string
     * @param {string} isoStr 
     * @returns {Date}
     */
    static fromISO(isoStr) {
        if (!isoStr) return null;
        // Handle "Z" or offset differences if needed, but Date.parse handles ISO well.
        // If the string has no offset, it might be treated as UTC or Local.
        // Python server returns ISO with offset usually.
        return new Date(isoStr);
    }

    /**
     * Format date to string in Browser's Local timezone (Server-agnostic)
     * @param {Date|string|number} date - Date object, ISO string, or timestamp (ms)
     * @param {object} options - Intl.DateTimeFormat options
     * @returns {string}
     */
    static format(date, options = {}) {
        if (!date) return '—';

        const d = this._toDate(date);
        if (isNaN(d.getTime())) return 'Invalid Date';

        const defaultOptions = {
            // timeZone: this.TIMEZONE, // Removed: use browser default
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        };

        try {
            return new Intl.DateTimeFormat('zh-CN', { ...defaultOptions, ...options }).format(d);
        } catch (e) {
            console.error('Time format error:', e);
            return String(d);
        }
    }

    /**
     * Format minimal time (e.g. 12:30:45)
     */
    static formatTime(date) {
        return this.format(date, {
            year: undefined,
            month: undefined,
            day: undefined
        });
    }

    /**
     * Format relative time (e.g. "5 minutes ago", "Yesterday 12:00")
     * Logic migrated from common.js but strictly using TimeUtils mechanics
     */
    static formatRelative(date) {
        const d = this._toDate(date);
        if (!d || isNaN(d.getTime())) return '未知时间';

        // Use synchronized now() for relative calculation
        const now = this.now();
        const diffMs = now - d;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) {
            // Check if it's strictly same day in Shanghai Time? 
            // Simple approach: if diff is small enough.
            // But "Yesterday" depends on calendar day.
            // Let's stick to the logic: if diffDays < 1... wait, manual calculation is shaky.
            // Better: Compare date strings.
            const todayStr = this.format(now, { hour: undefined, minute: undefined, second: undefined });
            const dateStr = this.format(d, { hour: undefined, minute: undefined, second: undefined });

            if (todayStr === dateStr) {
                return this.formatTime(d);
            }
            return this.format(d, { year: undefined, second: undefined }); // Month/Day Hour:Min
        }

        if (diffDays === 1) {
            return `昨天 ${this.formatTime(d).slice(0, 5)}`; // Simple hack, or use full format
        }

        if (diffDays < 7) {
            return `${diffDays}天前`;
        }

        // Full date
        return this.format(d, { hour: undefined, minute: undefined, second: undefined });
    }

    /* Internal helper */
    static _toDate(input) {
        if (input instanceof Date) return input;
        if (typeof input === 'string') return new Date(input);
        if (typeof input === 'number') return new Date(input); // Assumes ms if int
        return new Date(input);
    }
}

// Export for module systems or global
window.TimeUtils = TimeUtils;
