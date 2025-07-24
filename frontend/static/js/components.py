"""
UI Components for BingX Trading Bot Frontend
Handles rendering of different dashboard sections
"""

from datetime import datetime, timedelta
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
    def format_large_number(value):
        """Format large numbers with K/M/B suffixes"""
        if not value:
            return "-"
        
        try:
            value = float(value)
            if value == 0:
                return "-"
            
            if abs(value) >= 1_000_000_000:
                return f"${value/1_000_000_000:.1f}B"
            elif abs(value) >= 1_000_000:
                return f"${value/1_000_000:.1f}M"
            elif abs(value) >= 1_000:
                return f"${value/1_000:.1f}K"
            else:
                return f"${value:.2f}"
        except (ValueError, TypeError):
            return "-"
    
    @staticmethod
    def format_datetime(dt_str):
        """Format datetime string to local time (UTC-3)"""
        if not dt_str:
            return "-"
        try:
            # Handle different datetime formats that might come from backend
            if isinstance(dt_str, str):
                # Remove timezone suffix and normalize
                dt_str_clean = dt_str.replace('Z', '+00:00')
                
                # Try parsing ISO format first
                try:
                    dt = datetime.fromisoformat(dt_str_clean)
                except ValueError:
                    # Fallback: try parsing without timezone info (assume UTC)
                    dt = datetime.fromisoformat(dt_str.replace('Z', '').replace('+00:00', ''))
                    # Add UTC timezone info
                    from datetime import timezone
                    dt = dt.replace(tzinfo=timezone.utc)
            else:
                # Handle datetime objects directly
                dt = dt_str
                if dt.tzinfo is None:
                    from datetime import timezone
                    dt = dt.replace(tzinfo=timezone.utc)
            
            # Convert to UTC-3 (Brazil time)
            dt_utc3 = dt - timedelta(hours=3)
            return dt_utc3.strftime("%d/%m %H:%M")
        except (ValueError, AttributeError, TypeError) as e:
            # Log the error for debugging and return original string
            console.error(f"Error formatting datetime '{dt_str}': {e}")
            return str(dt_str) if dt_str else "-"
    
    @staticmethod
    def format_datetime_full(dt_str):
        """Format datetime string to full local time (UTC-3) with seconds"""
        if not dt_str:
            return "-"
        try:
            # Handle different datetime formats that might come from backend
            if isinstance(dt_str, str):
                # Remove timezone suffix and normalize
                dt_str_clean = dt_str.replace('Z', '+00:00')
                
                # Try parsing ISO format first
                try:
                    dt = datetime.fromisoformat(dt_str_clean)
                except ValueError:
                    # Fallback: try parsing without timezone info (assume UTC)
                    dt = datetime.fromisoformat(dt_str.replace('Z', '').replace('+00:00', ''))
                    # Add UTC timezone info
                    from datetime import timezone
                    dt = dt.replace(tzinfo=timezone.utc)
            else:
                # Handle datetime objects directly
                dt = dt_str
                if dt.tzinfo is None:
                    from datetime import timezone
                    dt = dt.replace(tzinfo=timezone.utc)
            
            # Convert to UTC-3 (Brazil time)
            dt_utc3 = dt - timedelta(hours=3)
            return dt_utc3.strftime("%d/%m/%Y %H:%M:%S")
        except (ValueError, AttributeError, TypeError) as e:
            # Log the error for debugging and return original string
            console.error(f"Error formatting datetime_full '{dt_str}': {e}")
            return str(dt_str) if dt_str else "-"
    
    @staticmethod
    def format_datetime_with_timezone(dt_str):
        """Format datetime string with timezone indicator"""
        if not dt_str:
            return "-"
        try:
            # Parse ISO format datetime (assumes UTC)
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            # Convert to UTC-3 (Brazil time)
            dt_utc3 = dt - timedelta(hours=3)
            return dt_utc3.strftime("%d/%m %H:%M") + " (UTC-3)"
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
    def get_asset_display_name(asset_data):
        """Get display name for asset from API data or fallback"""
        # Use asset_name from API if available
        if 'asset_name' in asset_data:
            return asset_data['asset_name']
        
        # Fallback to symbol parsing
        symbol = asset_data.get('symbol', '')
        return symbol.split('/')[0] if '/' in symbol else symbol
    
    @staticmethod
    def render_validation_table_row(asset_data):
        """Render validation table row"""
        if not asset_data:
            return ""
        
        # Extract data with safe conversions
        symbol = asset_data.get("symbol", "")
        asset_name = UIComponents.get_asset_display_name(asset_data)
        status = asset_data.get("validation_status", "PENDING")
        score = asset_data.get("validation_score", 0)
        last_updated = asset_data.get("last_updated", "")
        
        # Market data
        price = asset_data.get("current_price")
        volume = asset_data.get("volume_24h_quote") 
        change_percent = asset_data.get("price_change_percent_24h")
        spread = asset_data.get("spread_percent")
        risk = asset_data.get("risk_level", "UNKNOWN")
        volatility = asset_data.get("volatility_24h")
        quality = asset_data.get("data_quality_score", 0)
        priority = asset_data.get("priority_asset", False)
        trading_enabled = asset_data.get("trading_enabled", False)
        age_days = asset_data.get("age_days")
        
        # CSS classes
        status_class = f"status-{status.lower()}"
        risk_class = f"risk-{risk.lower()}"
        row_class = "priority-asset" if priority else ""
        
        # Format values with better fallbacks
        price_str = UIComponents.format_currency(price) if price is not None else "-"
        volume_str = UIComponents.format_large_number(volume) if volume is not None else "-"
        
        # Format percentage change with color
        if change_percent is not None:
            change_class = "positive" if change_percent >= 0 else "negative"
            change_str = f'<span class="{change_class}">{change_percent:+.2f}%</span>'
        else:
            change_str = "-"
            
        spread_str = f"{spread:.3f}%" if spread is not None else "-"
        volatility_str = f"{volatility:.1f}%" if volatility is not None else "-"
        age_str = f"{age_days}" if age_days is not None else "-"
        
        # Trading status
        trading_str = "✅" if trading_enabled else "❌"
        
        # Quality score as percentage
        quality_str = f"{quality}%" if quality is not None else "-"
        
        # Format timestamp
        last_updated_str = UIComponents.format_datetime_full(last_updated)
        
        row_html = f'''
        <tr class="{row_class}" data-symbol="{symbol}">
            <td>
                <div class="asset-info">
                    <div class="asset-symbol">{symbol} {'🌟' if priority else ''}</div>
                    <div class="asset-name">{asset_name}</div>
                </div>
            </td>
            <td class="{status_class}">{status}</td>
            <td>{score:.0f}</td>
            <td>{price_str}</td>
            <td onclick="sortTable('volume_24h_quote')" style="cursor: pointer;">{volume_str}</td>
            <td>{change_str}</td>
            <td>{spread_str}</td>
            <td class="{risk_class}">{risk}</td>
            <td>{trading_str}</td>
            <td>{quality_str}</td>
            <td class="timestamp">{last_updated_str}</td>
            <td>{age_str}</td>
        </tr>
        '''
        
        return row_html
    
    @staticmethod
    def update_validation_table(validation_data):
        """Update asset validation table with server-side data"""
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
            pagination = validation_data.get("pagination", {})
            console.log(f"DEBUG: table_data length: {len(table_data)}")
            
            if not table_data:
                tbody.innerHTML = '<tr><td colspan="15" style="text-align: center;">Nenhum ativo encontrado</td></tr>'
                return
            
            # Generate HTML for table rows
            rows_html = ""
            for asset in table_data:
                rows_html += UIComponents.render_validation_table_row(asset)
            
            tbody.innerHTML = rows_html
            
            # Update pagination info using server data
            UIComponents._update_server_pagination_info(pagination)
            
        except Exception as e:
            console.error(f"Error updating validation table: {str(e)}")
    
    @staticmethod
    def filter_validation_table():
        """Filter validation table using server-side filtering"""
        try:
            # Get filter states from UI
            show_only_valid = document.getElementById("show-only-valid")
            priority_only = document.getElementById("priority-only") 
            trading_enabled_only = document.getElementById("trading-enabled-only")
            risk_level_filter = document.getElementById("risk-level-filter")
            
            # Build filters object
            filters = {
                'filter_valid_only': show_only_valid.checked if show_only_valid else False,
                'priority_only': priority_only.checked if priority_only else False,
                'trading_enabled_only': trading_enabled_only.checked if trading_enabled_only else False,
                'risk_level_filter': risk_level_filter.value if risk_level_filter else "all"
            }
            
            console.log(f"Filter states: {filters}")
            
            # Call app method via global document
            try:
                from js import document
                if hasattr(document, 'applyValidationTableFilters'):
                    document.applyValidationTableFilters(filters)
                else:
                    console.error("applyValidationTableFilters not available on document")
            except Exception as e:
                console.error(f"Error calling applyValidationTableFilters: {e}")
            
        except Exception as e:
            console.error(f"Error filtering validation table: {str(e)}")
    
    
    @staticmethod
    def _update_server_pagination_info(pagination):
        """Update pagination information from server data"""
        try:
            current_page = pagination.get('current_page', 1)
            total_pages = pagination.get('total_pages', 1)
            total_records = pagination.get('total_records', 0)
            showing_records = pagination.get('showing_records', 0)
            
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
            
            # Store pagination state for other functions
            UIComponents._current_page = current_page
            UIComponents._total_pages = total_pages
                
        except Exception as e:
            console.error(f"Error updating server pagination: {str(e)}")
    
    @staticmethod
    def sort_validation_table(column, use_server_side=False):
        """Sort validation table using client-side sorting on currently loaded data"""
        try:
            # Allow fallback to server-side if needed
            if use_server_side:
                console.log(f"Using server-side sorting for column: {column}")
                UIComponents._sort_server_side(column)
                return
                
            console.log(f"Client-side sorting by column: {column}")
            
            # Get current table body
            tbody = document.getElementById("validation-table-body")
            if not tbody:
                console.error("Table body not found for sorting")
                # Fallback to server-side if client-side fails
                UIComponents._sort_server_side(column)
                return
            
            # Get all current rows
            rows = tbody.querySelectorAll("tr")
            if len(rows) == 0:
                console.log("No rows to sort")
                return
            
            # Toggle sort direction if same column
            current_sort_column = getattr(UIComponents, '_sort_column', None)
            current_sort_direction = getattr(UIComponents, '_sort_direction', 'asc')
            
            if current_sort_column == column:
                new_direction = 'desc' if current_sort_direction == 'asc' else 'asc'
            else:
                new_direction = 'asc'
            
            # Store sort state
            UIComponents._sort_column = column
            UIComponents._sort_direction = new_direction
            
            # Convert rows to list for sorting
            rows_list = []
            for i in range(len(rows)):
                rows_list.append(rows[i])
            
            # Get column index from table header
            column_index = UIComponents._get_column_index(column)
            if column_index == -1:
                console.error(f"Column {column} not found in table headers")
                return
            
            # Sort rows based on column content
            def sort_key(row):
                cells = row.querySelectorAll("td")
                if column_index < len(cells):
                    cell_text = cells[column_index].textContent.strip()
                    return UIComponents._get_sort_value(cell_text, column)
                return ""
            
            # Sort the rows
            reverse_order = (new_direction == 'desc')
            rows_list.sort(key=sort_key, reverse=reverse_order)
            
            # Clear tbody and re-append sorted rows
            tbody.innerHTML = ""
            for row in rows_list:
                tbody.appendChild(row)
            
            # Update visual indicators
            UIComponents._update_sort_indicators(column, new_direction)
            
            console.log(f"Table sorted by {column} ({new_direction})")
                    
        except Exception as e:
            console.error(f"Error sorting table: {str(e)}")
    
    @staticmethod
    def _get_column_index(column):
        """Get the index of a column in the table"""
        try:
            # Map column names to their positions in the table
            column_mapping = {
                "symbol": 0,
                "validation_status": 1, 
                "validation_score": 2,
                "current_price": 3,
                "volume_24h_quote": 4,
                "price_change_percent_24h": 5,
                "spread_percent": 6,
                "risk_level": 7,
                "trading_enabled": 8,
                "data_quality_score": 9,
                "last_updated": 10,
                "age_days": 11
            }
            return column_mapping.get(column, -1)
        except Exception as e:
            console.error(f"Error getting column index: {e}")
            return -1
    
    @staticmethod
    def _get_sort_value(cell_text, column):
        """Convert cell text to sortable value based on column type"""
        try:
            # Handle different data types for proper sorting
            if column in ["validation_score", "current_price", "volume_24h_quote", "spread_percent", "data_quality_score", "age_days"]:
                # Numeric columns - extract numbers
                import re
                numbers = re.findall(r'[\d,.-]+', cell_text.replace('$', '').replace('%', '').replace(',', ''))
                if numbers:
                    try:
                        return float(numbers[0])
                    except ValueError:
                        return 0
                return 0
            elif column == "price_change_percent_24h":
                # Handle percentage with + or - sign
                import re
                match = re.search(r'[+-]?[\d.]+', cell_text.replace('%', ''))
                if match:
                    try:
                        return float(match.group())
                    except ValueError:
                        return 0
                return 0
            else:
                # Text columns - return as is for alphabetical sorting
                return cell_text.lower()
        except Exception as e:
            console.error(f"Error getting sort value: {e}")
            return cell_text.lower() if cell_text else ""
    
    @staticmethod
    def _update_sort_indicators(column, direction):
        """Update visual sort indicators in table headers"""
        try:
            # Remove all existing sort indicators
            headers = document.querySelectorAll(".sortable")
            for header in headers:
                header.classList.remove("asc", "desc")
                # Remove existing sort arrows
                existing_arrows = header.querySelectorAll(".sort-arrow")
                for arrow in existing_arrows:
                    arrow.remove()
            
            # Add indicator to current column
            current_header = document.querySelector(f'.sortable[data-sort="{column}"]')
            if current_header:
                current_header.classList.add(direction)
                
                # Add visual arrow
                arrow = document.createElement("span")
                arrow.className = "sort-arrow"
                arrow.innerHTML = " ↓" if direction == "desc" else " ↑"
                current_header.appendChild(arrow)
                
        except Exception as e:
            console.error(f"Error updating sort indicators: {e}")
    
    @staticmethod
    def change_table_page(direction):
        """Change table page using server-side pagination"""
        try:
            current_page = getattr(UIComponents, '_current_page', 1)
            total_pages = getattr(UIComponents, '_total_pages', 1)
            
            new_page = current_page + direction
            if 1 <= new_page <= total_pages:
                # Use server-side pagination
                from js import document
                if hasattr(document, 'refreshValidationTablePage'):
                    document.refreshValidationTablePage(new_page)
                else:
                    console.warn("refreshValidationTablePage function not available")
                
        except Exception as e:
            console.error(f"Error changing page: {str(e)}")
    
    @staticmethod
    def export_validation_table():
        """Export validation table to CSV"""
        try:
            # Show notification that export is not available with server-side pagination
            UIComponents.show_notification(
                "Export",
                "Função de export será reimplementada em breve com paginação server-side",
                "info"
            )
            return
            
        except Exception as e:
            console.error(f"Error exporting table: {str(e)}")
    
    @staticmethod
    def show_notification(title, message, notification_type="info", duration=3000):
        """Show a dismissable notification with fast auto-hide."""
        try:
            notifications_container = document.getElementById("notifications")
            if not notifications_container:
                console.error("Notification container not found.")
                return

            # Prevent duplicate notifications
            existing_notifications = document.querySelectorAll(".notification-content p")
            for el in existing_notifications:
                if el.textContent == message:
                    console.log("Duplicate notification prevented.")
                    return

            # Create notification element
            notification = document.createElement("div")
            notification.className = f"notification notification-{notification_type}"
            
            # Create content container  
            content = document.createElement("div")
            content.className = "notification-content"
            
            title_element = document.createElement("h4")
            title_element.textContent = title
            
            message_element = document.createElement("p")
            message_element.textContent = message
            
            content.appendChild(title_element)
            content.appendChild(message_element)
            
            # Create close button
            close_button = document.createElement("button")
            close_button.className = "notification-close"
            close_button.innerHTML = "&times;"
            close_button.setAttribute("aria-label", "Fechar notificação")
            
            notification.appendChild(content)
            notification.appendChild(close_button)
            
            # Add to container
            notifications_container.appendChild(notification)
            
            # Enhanced removal function with animation
            def remove_notification():
                try:
                    if notification and notification.parentNode:
                        # Add fade-out class for smooth transition
                        notification.classList.add("fade-out")
                        
                        # Remove element after animation completes
                        def final_remove():
                            if notification and notification.parentNode:
                                notification.remove()
                        
                        # Wait for CSS transition to complete (300ms)
                        document.defaultView.setTimeout(create_proxy(final_remove), 300)
                        
                except Exception as e:
                    console.error(f"Error removing notification: {e}")

            # Manual close button
            from pyodide.ffi import create_proxy  
            close_button.addEventListener("click", create_proxy(remove_notification))
            
            # Auto-remove with type-specific durations for quick dismissal
            auto_hide_duration = duration
            if notification_type == "success":
                auto_hide_duration = 2000  # 2 seconds for success messages
            elif notification_type == "info":
                auto_hide_duration = 2500  # 2.5 seconds for info  
            elif notification_type == "warning":
                auto_hide_duration = 3500  # 3.5 seconds for warnings
            elif notification_type == "error":
                auto_hide_duration = 4000  # 4 seconds for errors (longer to read)
            
            # Set timeout for auto-removal
            document.defaultView.setTimeout(create_proxy(remove_notification), auto_hide_duration)
            
            console.log(f"Notification: '{title}' - auto-hide in {auto_hide_duration}ms")

        except Exception as e:
            console.error(f"Error showing notification: {str(e)}")

    @staticmethod
    def clear_all_notifications():
        """Clear all notifications immediately."""
        try:
            notifications_container = document.getElementById("notifications")
            if notifications_container:
                notifications_container.innerHTML = ""
                console.log("All notifications cleared")
        except Exception as e:
            console.error(f"Error clearing notifications: {e}")


# Global UI components instance
ui_components = UIComponents()

# Initialize validation table state storage
UIComponents._current_page = 1
UIComponents._total_pages = 1
UIComponents._sort_column = None 
UIComponents._sort_direction = 'asc'