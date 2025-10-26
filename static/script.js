class MusicPlayer {
    constructor() {
        this.audio = document.getElementById('audioPlayer');
        this.isPlaying = false;
        this.currentTrackIndex = 0;
        this.tracks = [];
        this.volume = 0.5;
        
        this.initializeEventListeners();
        this.loadInitialData();
    }

    initializeEventListeners() {
        this.audio.addEventListener('loadedmetadata', () => {
            this.updateDuration();
        });

        this.audio.addEventListener('timeupdate', () => {
            this.updateProgress();
        });

        this.audio.addEventListener('ended', () => {
            this.nextTrack();
        });

        // Обработчик клика по прогресс-бару
        document.getElementById('progressBar').addEventListener('click', (e) => {
            this.seek(e);
        });
    }

    loadInitialData() {
        const urlParams = new URLSearchParams(window.location.search);
        const searchQuery = urlParams.get('search');
        if (searchQuery) {
            document.getElementById('searchInput').value = searchQuery;
            this.searchMusic();
        }
    }

    async searchMusic() {
        const query = document.getElementById('searchInput').value.trim();
        if (!query) return;

        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            this.tracks = await response.json();
            this.displayTracks();
        } catch (error) {
            console.error('Search error:', error);
            this.showMessage('Ошибка при поиске музыки');
        }
    }

    displayTracks() {
        const playlist = document.getElementById('playlist');
        playlist.innerHTML = '';

        this.tracks.forEach((track, index) => {
            const trackElement = document.createElement('div');
            trackElement.className = 'track-item';
            trackElement.innerHTML = `
                <img src="${track.cover || '/static/default-cover.png'}" alt="Обложка">
                <div class="track-info-small">
                    <h4>${this.escapeHtml(track.title)}</h4>
                    <p>${this.escapeHtml(track.artist)}</p>
                </div>
                <button class="play-btn-small" onclick="player.playTrack(${index})">▶️</button>
            `;
            playlist.appendChild(trackElement);
        });
    }

    async playTrack(index) {
        this.currentTrackIndex = index;
        const track = this.tracks[index];
        
        try {
            const response = await fetch(`/api/track/${track.id}`);
            const data = await response.json();
            
            if (data.url) {
                this.audio.src = data.url;
                this.updateTrackInfo(track);
                this.togglePlay();
            } else {
                this.showMessage('Не удалось загрузить трек');
            }
        } catch (error) {
            console.error('Play error:', error);
            this.showMessage('Ошибка при воспроизведении');
        }
    }

    updateTrackInfo(track) {
        document.getElementById('currentTrack').textContent = track.title;
        document.getElementById('currentArtist').textContent = track.artist;
        
        const albumImage = document.getElementById('albumImage');
        if (track.cover) {
            albumImage.src = track.cover;
            albumImage.style.display = 'block';
        } else {
            albumImage.style.display = 'none';
        }
    }

    togglePlay() {
        if (this.audio.src) {
            if (this.isPlaying) {
                this.audio.pause();
            } else {
                this.audio.play();
            }
            this.isPlaying = !this.isPlaying;
            this.updatePlayButton();
        }
    }

    updatePlayButton() {
        const playBtn = document.querySelector('.play-btn');
        playBtn.textContent = this.isPlaying ? '⏸️' : '▶️';
    }

    nextTrack() {
        if (this.tracks.length > 0) {
            this.currentTrackIndex = (this.currentTrackIndex + 1) % this.tracks.length;
            this.playTrack(this.currentTrackIndex);
        }
    }

    previousTrack() {
        if (this.tracks.length > 0) {
            this.currentTrackIndex = (this.currentTrackIndex - 1 + this.tracks.length) % this.tracks.length;
            this.playTrack(this.currentTrackIndex);
        }
    }

    updateProgress() {
        const progress = document.getElementById('progress');
        const currentTime = document.getElementById('currentTime');
        const duration = document.getElementById('duration');
        
        if (this.audio.duration) {
            const percent = (this.audio.currentTime / this.audio.duration) * 100;
            progress.style.width = percent + '%';
            
            currentTime.textContent = this.formatTime(this.audio.currentTime);
            duration.textContent = this.formatTime(this.audio.duration);
        }
    }

    updateDuration() {
        document.getElementById('duration').textContent = this.formatTime(this.audio.duration);
    }

    seek(e) {
        const progressBar = document.getElementById('progressBar');
        const percent = e.offsetX / progressBar.offsetWidth;
        this.audio.currentTime = percent * this.audio.duration;
    }

    setVolume(value) {
        this.volume = value / 100;
        this.audio.volume = this.volume;
    }

    toggleMute() {
        this.audio.muted = !this.audio.muted;
        const muteBtn = document.querySelector('.control-btn:nth-child(4)');
        muteBtn.textContent = this.audio.muted ? '🔇' : '🔊';
    }

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showMessage(message) {
        // Можно добавить красивые уведомления
        alert(message);
    }
}

// Глобальные функции для кнопок
function searchMusic() {
    player.searchMusic();
}

function togglePlay() {
    player.togglePlay();
}

function nextTrack() {
    player.nextTrack();
}

function previousTrack() {
    player.previousTrack();
}

function setVolume(value) {
    player.setVolume(value);
}

function toggleMute() {
    player.toggleMute();
}

// Поиск при нажатии Enter
document.getElementById('searchInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        searchMusic();
    }
});

// Инициализация плеера
const player = new MusicPlayer();
