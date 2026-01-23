import React from 'react';

interface VideoPlayerProps {
  title: string;
  subtitle: string;
  videoSrc: string;
  posterSrc?: string;
  captionsSrc?: string;
  id?: string;
}

const VideoPlayer: React.FC<VideoPlayerProps> = ({
  title,
  subtitle,
  videoSrc,
  posterSrc,
  captionsSrc,
  id = 'video',
}) => {
  return (
    <section className="video-player" id={id}>
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">{title}</h2>
          <p className="section-subtitle">{subtitle}</p>
        </div>
        <div className="video-container">
          <div className="video-wrapper">
            <video
              className="video-element"
              controls
              preload="metadata"
              poster={posterSrc}
              aria-label={`${title}: ${subtitle}`}
            >
              <source src={videoSrc} type="video/mp4" />
              {captionsSrc && (
                <track kind="captions" src={captionsSrc} srcLang="en" label="English captions" />
              )}
              Your browser does not support the video tag.
            </video>
          </div>
        </div>
      </div>
    </section>
  );
};

export default VideoPlayer;
