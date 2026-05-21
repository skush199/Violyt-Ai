import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { ReactNode } from "react"

export function Tooltips({children, content}: {
    children: ReactNode,
    content?: string
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {children}
      </TooltipTrigger>
      <TooltipContent>
        {
            content &&  <p>{content}</p>
        }
      </TooltipContent>
    </Tooltip>
  )
}
