import { cn } from '@/lib/utils';
import { HTMLAttributes, forwardRef } from 'react';

export const Badge = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement> & { variant?: 'default' | 'secondary' | 'outline' | 'success' | 'warning' | 'danger' }>(
  ({ className, variant = 'default', ...props }, ref) => {
    const v = {
      default: 'bg-primary text-primary-foreground',
      secondary: 'bg-secondary text-secondary-foreground',
      outline: 'border text-foreground',
      success: 'bg-emerald-100 text-emerald-800',
      warning: 'bg-amber-100 text-amber-800',
      danger: 'bg-red-100 text-red-800',
    };
    return <div ref={ref} className={cn('inline-flex items-center rounded-full border border-transparent px-2 py-0.5 text-xs font-medium', v[variant], className)} {...props} />;
  }
);
Badge.displayName = 'Badge';
