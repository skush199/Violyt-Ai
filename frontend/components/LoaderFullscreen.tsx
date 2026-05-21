import React from 'react'

const LoaderFullscreen = () => {
    return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
            <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
                <p className="text-primary">Loading...</p>
            </div>
        </div>
    )
}

export default LoaderFullscreen
