import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { ReactNode } from "react"

export function NotificationDrawer({ children }: { children: ReactNode }) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        {children}
      </SheetTrigger>
      <SheetContent className="font-dmSans">
        <SheetHeader>
          <SheetTitle className="text-primary text-2xl font-bold">Notification</SheetTitle>
          <SheetDescription className="sr-only">
            View your recent notifications and updates.
          </SheetDescription>
        </SheetHeader>
        <div className="grid flex-1 auto-rows-min gap-6 px-4">
            {
                [0,1].map((_, index) => (
                    <div key={index} className="border border-[#DCDCDC] p-4 rounded-xl shadow-sm">
                        <div className="flex items-center justify-between">
                        <h1 className="text-lg text-primary font-medium">notification title</h1>
                        <span className="text-sm text-gray-400">10 min ago</span>
                        </div>
                        <p className="text-sm text-[#525252]">Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the</p>
                    </div>
                ))
            }
        </div>
        <SheetFooter>
          <SheetClose asChild>
            <Button variant="outline" className="w-full">Clear All</Button>
          </SheetClose>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
