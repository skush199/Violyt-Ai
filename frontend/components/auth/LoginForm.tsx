'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Eye, EyeOff } from 'lucide-react';
import { useLogin } from '@/hooks/useLogin';
import { getApiErrorMessage } from '@/lib/api/error-message';

export function LoginForm() {
  const router = useRouter();
  const { mutate: login, isPending, error } = useLogin();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    event.stopPropagation();

    login(
      {
        email,
        password,
      },
      {
        onSuccess: (response) => {
          if ('requires_two_factor' in response && response.requires_two_factor) {
            router.replace('/auth/verify-2fa');
            return;
          }
          router.replace('/dashboard');
        },
      },
    );
  };

  return (
    <form onSubmit={handleSubmit} className="w-full space-y-6">
      <div className="space-y-2">
        <label htmlFor="email" className="text-base font-normal leading-6 text-[#121212]">
          Work Email
        </label>
        <Input
          id="email"
          type="email"
          placeholder="Enter your work email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          disabled={isPending}
          className="h-12 rounded-none border-none bg-[#F5F7FA] px-4 text-sm text-[#121212] placeholder:text-[#8C8C8C] focus-visible:ring-2 focus-visible:ring-primary/20"
        />
      </div>

      <div className="space-y-3">
        <div className="space-y-2">
          <label htmlFor="password" className="text-base font-normal leading-6 text-[#121212]">
            Password
          </label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={isPending}
              className="h-12 rounded-none border-none bg-[#F5F7FA] px-4 pr-11 text-sm text-[#121212] placeholder:text-[#8C8C8C] focus-visible:ring-2 focus-visible:ring-primary/20"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7A7A7A] transition hover:text-[#4B5563]"
              tabIndex={-1}
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between gap-4">
          <label htmlFor="remember" className="flex cursor-pointer items-center gap-2 text-sm font-medium text-[#3D3D3D]">
            <Checkbox
              id="remember"
              checked={rememberMe}
              onCheckedChange={(checked) => setRememberMe(checked as boolean)}
              disabled={isPending}
            />
            <span>Keep me signed in</span>
          </label>
          <Link href="/auth/forgot-password" className="text-sm font-medium text-primary transition hover:text-primary/80">
            Forgot password?
          </Link>
        </div>
      </div>

      {error ? <div className="text-sm text-red-500">{getApiErrorMessage(error, 'Login failed')}</div> : null}

      <Button
        type="submit"
        disabled={isPending || !email || !password}
        className="h-12 w-full rounded-none bg-primary text-base font-bold text-white hover:bg-primary/90"
      >
        {isPending ? 'Signing in...' : 'Access Workspace'}
      </Button>

      <p className="text-base leading-6 text-[#3D3D3D]">
        Secure access to your brand intelligence environment.
      </p>
    </form>
  );
}
