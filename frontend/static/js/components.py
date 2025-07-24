"""
UI Components for BingX Trading Bot Frontend
Handles rendering of different dashboard sections
"""

from datetime import datetime
from js import document, console


class UIComponents:
    @staticmethod
    def format_currency(value, currency="$"):
        """Format currency value"""
        if value is None:
            return f"{currency}0.00"
        try:
            return f"{currency}{float(value):,.2f}"
        except (ValueError, TypeError):
            return f"{currency}0.00"
    
    @staticmethod
    def format_percentage(value):
        """Format percentage value"""
        if value is None:
            return "0.00%"
        try:
            return f"{float(value):+.2f}%"
        except (ValueError, TypeError):
            return "0.00%"
    
    @staticmethod
    def format_datetime(dt_str):
        """Format datetime string"""
        if not dt_str:
            return "-"
        try:
            # Parse ISO format datetime
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            return dt.strftime("%d/%m %H:%M")
        except (ValueError, AttributeError):
            return dt_str
    
    @staticmethod
    def get_signal_class(signal_type):
        """Get CSS class for signal type"""
        if signal_type in ["COMPRA", "BUY"]:
            return "buy"
        elif signal_type in ["VENDA", "SELL"]:
            return "sell"
        else:
            return "neutral"
    
    @staticmethod
    def get_pnl_class(value):
        """Get CSS class for P&L value"""
        try:
            val = float(value)
            if val > 0:
                return "positive"
            elif val < 0:
                return "negative"
            else:
                return ""
        except (ValueError, TypeError):
            return ""
    
    @staticmethod
    def render_asset_card(symbol, indicator_data):
        """Render asset card for scanner tab"""
        if not indicator_data:
            return ""
        
        # Get the latest indicator data
        timeframe = indicator_data.get("timeframe", "1h")
        price = indicator_data.get("price", 0)
        mm1 = indicator_data.get("mm1", 0)
        center = indicator_data.get("center", 0)
        rsi = indicator_data.get("rsi", 50)
        volume_ratio = indicator_data.get("volume_ratio", 1)
        timestamp = indicator_data.get("timestamp", "")
        
        # Determine signal based on MM1 vs Center
        signal = ""
        signal_class = "neutral"
        if mm1 and center:
            if mm1 > center:
                signal = "COMPRA"
                signal_class = "buy"
            elif mm1 < center:
                signal = "VENDA" 
                signal_class = "sell"
        
        # Calculate strength based on distance and RSI
        strength = 0
        if mm1 and center and price:
            distance = abs(mm1 - center) / center * 100
            rsi_strength = 1 - abs(rsi - 50) / 50  # Closer to 50 = lower strength
            strength = min(distance * rsi_strength * 10, 100)
        
        card_html = f'''
        <div class="asset-card {signal_class}">
            <div class="card-header">
                <h3>{symbol}</h3>
                <span class="timestamp">{UIComponents.format_datetime(timestamp)}</span>
            </div>
            
            <div class="indicators-grid">
                <div class="timeframe">
                    <h4>{timeframe}</h4>
                    <div>Preço: {UIComponents.format_currency(price)}</div>
                    <div>MM1: {UIComponents.format_currency(mm1)}</div>
                    <div>Center: {UIComponents.format_currency(center)}</div>
                    <div>RSI: {rsi:.1f}</div>
                </div>
                <div class="timeframe">
                    <h4>Volume</h4>
                    <div>Ratio: {volume_ratio:.2f}x</div>
                    <div>Status: {"Alto" if volume_ratio > 1.5 else "Normal"}</div>
                </div>
                <div class="timeframe">
                    <h4>Sinal</h4>
                    <div class="signal-type {signal_class}">{signal or "NEUTRO"}</div>
                    <div>Força: {strength:.0f}%</div>
                </div>
            </div>
        </div>
        '''
        
        return card_html
    
    @staticmethod
    def render_position_row(position):
        """Render position table row"""
        if not position:
            return ""
        
        symbol = position.get("symbol", "")
        side = position.get("side", "")
        amount = position.get("amount", 0)
        entry_price = position.get("entry_price", 0)
        current_price = position.get("current_price", 0)
        unrealized_pnl = position.get("unrealized_pnl", 0)
        stop_loss_price = position.get("stop_loss_price", 0)
        take_profit_price = position.get("take_profit_price", 0)
        status = position.get("status", "")
        
        # Calculate PnL percentage
        pnl_percentage = 0
        if entry_price and current_price:
            if side.upper() == "BUY":
                pnl_percentage = ((current_price - entry_price) / entry_price) * 100
            else:
                pnl_percentage = ((entry_price - current_price) / entry_price) * 100
        
        pnl_class = UIComponents.get_pnl_class(unrealized_pnl)
        side_class = "buy-side" if side.upper() == "BUY" else "sell-side"
        
        row_html = f'''
        <tr>
            <td>{symbol}</td>
            <td class="{side_class}">{side.upper()}</td>
            <td>{UIComponents.format_currency(entry_price)}</td>
            <td>{UIComponents.format_currency(current_price)}</td>
            <td class="{pnl_class}">
                {UIComponents.format_currency(unrealized_pnl)} 
                ({UIComponents.format_percentage(pnl_percentage)})
            </td>
            <td>{UIComponents.format_currency(stop_loss_price) if stop_loss_price else "-"}</td>
            <td>{UIComponents.format_currency(take_profit_price) if take_profit_price else "-"}</td>
            <td>{status.upper()}</td>
            <td>
                <button onclick="closePosition('{position.get('id', '')}')" class="btn-small btn-danger">
                    Fechar
                </button>
            </td>
        </tr>
        '''
        
        return row_html
    
    @staticmethod
    def render_trade_row(trade):
        """Render trade history table row"""
        if not trade:
            return ""
        
        created_at = trade.get("created_at", "")
        symbol = trade.get("symbol", "")
        side = trade.get("side", "")
        amount = trade.get("amount", 0)
        price = trade.get("price", 0)
        status = trade.get("status", "")
        
        side_class = "buy-side" if side.upper() == "BUY" else "sell-side"
        
        row_html = f'''
        <tr>
            <td>{UIComponents.format_datetime(created_at)}</td>
            <td>{symbol}</td>
            <td class="{side_class}">{side.upper()}</td>
            <td>{amount}</td>
            <td>{UIComponents.format_currency(price)}</td>
            <td>{status.upper()}</td>
        </tr>
        '''
        
        return row_html
    
    @staticmethod
    def update_stats_cards(data):
        """Update statistics cards"""
        try:
            summary = data.get("summary", {})
            
            # Update validation stats
            valid_assets = summary.get("valid_assets", 0)
            active_signals = summary.get("active_signals", 0)
            active_positions = summary.get("active_positions", 0)
            total_pnl = summary.get("total_unrealized_pnl", 0)
            recent_trades = summary.get("recent_trades_count", 0)
            
            # Update DOM elements
            elements = {
                "valid-assets-count": str(valid_assets),
                "active-signals-count": str(active_signals),
                "open-positions": str(active_positions),
                "trades-today": str(recent_trades),
                "last-update": UIComponents.format_datetime(data.get("timestamp", ""))
            }
            
            for element_id, value in elements.items():
                element = document.getElementById(element_id)
                if element:
                    element.textContent = value
            
            # Update P&L with color
            pnl_element = document.getElementById("total-pnl")
            if pnl_element:
                pnl_element.textContent = UIComponents.format_currency(total_pnl)
                pnl_element.className = f"pnl-value {UIComponents.get_pnl_class(total_pnl)}"
                
        except Exception as e:
            console.error(f"Error updating stats cards: {str(e)}")
    
    @staticmethod
    def update_scanner_grid(indicators_data):
        """Update scanner grid with latest indicators"""
        try:
            scanner_grid = document.getElementById("scanner-grid")
            if not scanner_grid:
                return
            
            # Group indicators by symbol
            indicators_by_symbol = {}
            for indicator in indicators_data:
                symbol = indicator.get("symbol", "")
                if symbol:
                    indicators_by_symbol[symbol] = indicator
            
            # Generate HTML for all asset cards
            cards_html = ""
            for symbol, indicator_data in indicators_by_symbol.items():
                cards_html += UIComponents.render_asset_card(symbol, indicator_data)
            
            scanner_grid.innerHTML = cards_html
            
        except Exception as e:
            console.error(f"Error updating scanner grid: {str(e)}")
    
    @staticmethod
    def update_positions_table(positions_data):
        """Update positions table"""
        try:
            tbody = document.getElementById("positions-tbody")
            if not tbody:
                return
            
            if not positions_data:
                tbody.innerHTML = '<tr><td colspan="9" style="text-align: center;">Nenhuma posição ativa</td></tr>'
                return
            
            rows_html = ""
            for position in positions_data:
                rows_html += UIComponents.render_position_row(position)
            
            tbody.innerHTML = rows_html
            
        except Exception as e:
            console.error(f"Error updating positions table: {str(e)}")
    
    @staticmethod
    def update_trades_table(trades_data):
        """Update trades history table"""
        try:
            tbody = document.getElementById("trades-tbody")
            if not tbody:
                return
            
            if not trades_data:
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">Nenhum trade encontrado</td></tr>'
                return
            
            rows_html = ""
            for trade in trades_data:
                rows_html += UIComponents.render_trade_row(trade)
            
            tbody.innerHTML = rows_html
            
        except Exception as e:
            console.error(f"Error updating trades table: {str(e)}")
    
    @staticmethod
    def render_validation_table_row(asset_data):
        """Render validation table row"""
        if not asset_data:
            return ""
        
        # Extract data with fallbacks
        symbol = asset_data.get("symbol", "")
        status = asset_data.get("validation_status", "PENDING")
        score = asset_data.get("validation_score", 0)
        price = asset_data.get("current_price")
        volume = asset_data.get("volume_24h_quote")
        spread = asset_data.get("spread_percent")
        rsi_2h = asset_data.get("rsi_2h")
        rsi_4h = asset_data.get("rsi_4h")
        ma_dir_2h = asset_data.get("ma_direction_2h", "")
        ma_dir_4h = asset_data.get("ma_direction_4h", "")
        signal_2h = asset_data.get("signal_2h", "")
        signal_4h = asset_data.get("signal_4h", "")
        risk = asset_data.get("risk_level", "UNKNOWN")
        volatility = asset_data.get("volatility_24h")
        quality = asset_data.get("data_quality_score", 0)
        priority = asset_data.get("priority_asset", False)
        
        # CSS classes
        status_class = f"status-{status.lower()}"
        risk_class = f"risk-{risk.lower()}"
        row_class = "priority-asset" if priority else ""
        
        # Format values
        price_str = UIComponents.format_currency(price) if price else "-"
        volume_str = UIComponents.format_currency(volume, "") if volume else "-"
        spread_str = f"{spread:.3f}" if spread else "-"
        rsi_2h_str = f"{rsi_2h:.1f}" if rsi_2h else "-"
        rsi_4h_str = f"{rsi_4h:.1f}" if rsi_4h else "-"
        volatility_str = f"{volatility:.1f}" if volatility else "-"
        
        # Direction indicators
        dir_2h_class = f"direction-{ma_dir_2h.lower()}" if ma_dir_2h else ""
        dir_4h_class = f"direction-{ma_dir_4h.lower()}" if ma_dir_4h else ""
        
        # Signal indicators
        signal_2h_class = f"signal-{signal_2h.lower()}" if signal_2h else "signal-none"
        signal_4h_class = f"signal-{signal_4h.lower()}" if signal_4h else "signal-none"
        
        row_html = f'''
        <tr class="{row_class}" data-symbol="{symbol}">
            <td>{symbol} {'🌟' if priority else ''}</td>
            <td class="{status_class}">{status}</td>
            <td>{score:.0f}</td>
            <td>{price_str}</td>
            <td>{volume_str}</td>
            <td>{spread_str}</td>
            <td>{rsi_2h_str}</td>
            <td>{rsi_4h_str}</td>
            <td class="{dir_2h_class}">{ma_dir_2h or "-"}</td>
            <td class="{dir_4h_class}">{ma_dir_4h or "-"}</td>
            <td class="{signal_2h_class}">{signal_2h or "-"}</td>
            <td class="{signal_4h_class}">{signal_4h or "-"}</td>
            <td class="{risk_class}">{risk}</td>
            <td>{volatility_str}</td>
            <td>{quality:.0f}%</td>
        </tr>
        '''
        
        return row_html
    
    @staticmethod
    def update_validation_table(validation_data):
        """Update asset validation table"""
        try:
            console.log("DEBUG: validation_data received:", validation_data)
            
            tbody = document.getElementById("validation-table-body")
            if not tbody:
                console.error("Validation table body not found")
                return
            
            if not validation_data:
                console.error("validation_data is None")
                tbody.innerHTML = '<tr><td colspan="15" style="text-align: center;">Erro: dados não recebidos</td></tr>'
                return
            
            table_data = validation_data.get("table_data", [])
            console.log(f"DEBUG: table_data length: {len(table_data)}")
            
            if not table_data:
                tbody.innerHTML = '<tr><td colspan="15" style="text-align: center;">Nenhum ativo encontrado</td></tr>'
                return
            
            # Store data for sorting and pagination
            UIComponents._validation_data = table_data
            UIComponents._original_data = table_data.copy()  # Keep original data
            UIComponents._current_page = 1
            UIComponents._items_per_page = 25
            UIComponents._sort_column = None
            UIComponents._sort_direction = 'asc'
            
            # Apply current filters
            UIComponents.filter_validation_table()
            
        except Exception as e:
            console.error(f"Error updating validation table: {str(e)}")
    
    @staticmethod
    def filter_validation_table():
        """Filter validation table based on checkbox states"""
        try:
            if not hasattr(UIComponents, '_original_data'):
                return
            
            # Get filter states
            show_only_valid = document.getElementById("show-only-valid")
            show_only_with_signals = document.getElementById("show-only-with-signals")
            priority_only = document.getElementById("priority-only")
            
            only_valid = show_only_valid.checked if show_only_valid else True
            only_with_signals = show_only_with_signals.checked if show_only_with_signals else False
            priority_filter = priority_only.checked if priority_only else False
            
            # Start with original data
            filtered_data = UIComponents._original_data.copy()
            
            # Apply filters
            if only_valid:
                filtered_data = [item for item in filtered_data if item.get("validation_status") == "VALID"]
            
            if only_with_signals:
                filtered_data = [item for item in filtered_data 
                               if item.get("signal_2h") or item.get("signal_4h")]
            
            if priority_filter:
                filtered_data = [item for item in filtered_data if item.get("priority_asset", False)]
            
            # Update stored data and re-render
            UIComponents._validation_data = filtered_data
            UIComponents._current_page = 1
            UIComponents._render_validation_page()
            UIComponents._update_pagination_info()
            
            # Update total symbols count
            total_element = document.getElementById("total-symbols-count")
            if total_element:
                total_element.textContent = str(len(UIComponents._original_data))
            
        except Exception as e:
            console.error(f"Error filtering validation table: {str(e)}")
    
    @staticmethod
    def _render_validation_page():
        """Render current page of validation table"""
        try:
            tbody = document.getElementById("validation-table-body")
            if not tbody or not hasattr(UIComponents, '_validation_data'):
                return
            
            data = UIComponents._validation_data
            page = UIComponents._current_page
            per_page = UIComponents._items_per_page
            
            # Calculate pagination
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_data = data[start_idx:end_idx]
            
            # Generate HTML
            rows_html = ""
            for asset in page_data:
                rows_html += UIComponents.render_validation_table_row(asset)
            
            tbody.innerHTML = rows_html
            
        except Exception as e:
            console.error(f"Error rendering validation page: {str(e)}")
    
    @staticmethod
    def _update_pagination_info():
        """Update pagination information"""
        try:
            if not hasattr(UIComponents, '_validation_data'):
                return
            
            total_items = len(UIComponents._validation_data)
            current_page = UIComponents._current_page
            per_page = UIComponents._items_per_page
            total_pages = max(1, (total_items + per_page - 1) // per_page)
            
            # Update page info
            page_info = document.getElementById("page-info")
            if page_info:
                page_info.textContent = f"Página {current_page} de {total_pages}"
            
            # Update button states
            prev_btn = document.querySelector(".pagination button:first-child")
            next_btn = document.querySelector(".pagination button:last-child")
            
            if prev_btn:
                prev_btn.disabled = current_page <= 1
            if next_btn:
                next_btn.disabled = current_page >= total_pages
                
        except Exception as e:
            console.error(f"Error updating pagination: {str(e)}")
    
    @staticmethod
    def sort_validation_table(column):
        """Sort validation table by column"""
        try:
            if not hasattr(UIComponents, '_validation_data'):
                return
            
            # Toggle sort direction if same column
            if UIComponents._sort_column == column:
                UIComponents._sort_direction = 'desc' if UIComponents._sort_direction == 'asc' else 'asc'
            else:
                UIComponents._sort_column = column
                UIComponents._sort_direction = 'asc'
            
            # Sort data
            reverse = UIComponents._sort_direction == 'desc'
            
            def get_sort_value(item):
                value = item.get(column)
                if value is None:
                    return 0 if isinstance(value, (int, float)) else ""
                return value
            
            UIComponents._validation_data.sort(key=get_sort_value, reverse=reverse)
            
            # Reset to first page and re-render
            UIComponents._current_page = 1
            UIComponents._render_validation_page()
            UIComponents._update_pagination_info()
            
            # Update header indicators
            headers = document.querySelectorAll(".sortable")
            for header in headers:
                header.classList.remove("asc", "desc")
                if header.getAttribute("data-sort") == column:
                    header.classList.add(UIComponents._sort_direction)
                    
        except Exception as e:
            console.error(f"Error sorting table: {str(e)}")
    
    @staticmethod
    def change_table_page(direction):
        """Change table page"""
        try:
            if not hasattr(UIComponents, '_validation_data'):
                return
            
            total_items = len(UIComponents._validation_data)
            per_page = UIComponents._items_per_page
            total_pages = max(1, (total_items + per_page - 1) // per_page)
            
            new_page = UIComponents._current_page + direction
            if 1 <= new_page <= total_pages:
                UIComponents._current_page = new_page
                UIComponents._render_validation_page()
                UIComponents._update_pagination_info()
                
        except Exception as e:
            console.error(f"Error changing page: {str(e)}")
    
    @staticmethod
    def export_validation_table():
        """Export validation table to CSV"""
        try:
            if not hasattr(UIComponents, '_validation_data'):
                console.warn("No validation data to export")
                return
            
            data = UIComponents._validation_data
            
            # CSV headers
            headers = [
                "Symbol", "Status", "Score", "Price", "Volume_24h", "Spread_%",
                "RSI_2h", "RSI_4h", "MA_Dir_2h", "MA_Dir_4h", "Signal_2h", "Signal_4h",
                "Risk_Level", "Volatility_24h", "Data_Quality", "Priority"
            ]
            
            # Generate CSV content
            csv_lines = [headers.join(",")]
            
            for asset in data:
                row = [
                    asset.get("symbol", ""),
                    asset.get("validation_status", ""),
                    str(asset.get("validation_score", 0)),
                    str(asset.get("current_price", "")),
                    str(asset.get("volume_24h_quote", "")),
                    str(asset.get("spread_percent", "")),
                    str(asset.get("rsi_2h", "")),
                    str(asset.get("rsi_4h", "")),
                    asset.get("ma_direction_2h", ""),
                    asset.get("ma_direction_4h", ""),
                    asset.get("signal_2h", ""),
                    asset.get("signal_4h", ""),
                    asset.get("risk_level", ""),
                    str(asset.get("volatility_24h", "")),
                    str(asset.get("data_quality_score", "")),
                    str(asset.get("priority_asset", False))
                ]
                csv_lines.append(row.join(","))
            
            csv_content = csv_lines.join("\n")
            
            # Create and download file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"asset_validation_{timestamp}.csv"
            
            # Create blob and download link
            from js import Blob, URL, document
            blob = Blob.new([csv_content], {"type": "text/csv"})
            url = URL.createObjectURL(blob)
            
            # Create temporary download link
            link = document.createElement("a")
            link.href = url
            link.download = filename
            link.style.display = "none"
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            URL.revokeObjectURL(url)
            
        except Exception as e:
            console.error(f"Error exporting table: {str(e)}")
    
    @staticmethod
    def show_notification(title, message, notification_type="info"):
        """Show notification"""
        try:
            notifications_container = document.getElementById("notifications")
            if not notifications_container:
                return
            
            notification_id = f"notification-{datetime.now().timestamp()}"
            
            notification_html = f'''
            <div id="{notification_id}" class="notification notification-{notification_type}">
                <h4>{title}</h4>
                <p>{message}</p>
            </div>
            '''
            
            notifications_container.innerHTML += notification_html
            
            # Auto-remove after 5 seconds
            setTimeout = document.defaultView.setTimeout
            def remove_notification():
                notification = document.getElementById(notification_id)
                if notification:
                    notification.remove()
            
            from pyodide.ffi import create_proxy
            setTimeout(create_proxy(remove_notification), 5000)
            
        except Exception as e:
            console.error(f"Error showing notification: {str(e)}")


# Global UI components instance
ui_components = UIComponents()

# Initialize validation table data storage
UIComponents._validation_data = []
UIComponents._original_data = []
UIComponents._current_page = 1
UIComponents._items_per_page = 25
UIComponents._sort_column = None
UIComponents._sort_direction = 'asc'