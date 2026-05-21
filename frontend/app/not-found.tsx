// This is Not found page

import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-screen">
      <h1 className="text-4xl font-bold mb-4">404 - Not Found</h1>
      <p className="text-lg text-gray-600">The page you are looking for does not exist.</p>
      <Button className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
        <Link href="/" className="text-slate-100 hover:underline">Go back to Home</Link>
      </Button>
    </div>
  );
}
